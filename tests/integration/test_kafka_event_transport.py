import os
import time
import uuid

from kafka import KafkaConsumer, KafkaProducer


bootstrap = os.environ["KAFKA_BOOTSTRAP_SERVERS"]
topic = f"tinyd-ci-events-{uuid.uuid4().hex}"
group_id = f"tinyd-ci-{uuid.uuid4().hex}"
expected = "tenant-a|event-1|execution-1"
producer = KafkaProducer(
    bootstrap_servers=bootstrap,
    value_serializer=lambda value: value.encode(),
)
consumer = KafkaConsumer(
    bootstrap_servers=bootstrap,
    auto_offset_reset="earliest",
    enable_auto_commit=False,
    group_id=group_id,
    value_deserializer=lambda value: value.decode(),
)

try:
    # Subscribe first so the consumer has a chance to join the group and
    # receive partition assignment before the producer publishes the event.
    consumer.subscribe([topic])
    assignment_deadline = time.monotonic() + 10
    while not consumer.assignment():
        if time.monotonic() >= assignment_deadline:
            raise AssertionError("Kafka consumer did not receive partition assignment")
        consumer.poll(timeout_ms=250)

    producer.send(topic, value=expected).get(timeout=10)
    producer.flush(timeout=10)

    deadline = time.monotonic() + 10
    values = []
    while time.monotonic() < deadline and expected not in values:
        records = consumer.poll(timeout_ms=250)
        values.extend(message.value for messages in records.values() for message in messages)

    assert expected in values, f"Kafka event not received: expected={expected!r}, values={values!r}"
finally:
    consumer.close()
    producer.close()
