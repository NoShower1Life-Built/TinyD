import os
import time
import uuid

from kafka import KafkaConsumer, KafkaProducer
from kafka.admin import KafkaAdminClient, NewTopic
from kafka.errors import TopicAlreadyExistsError


bootstrap = os.environ["KAFKA_BOOTSTRAP_SERVERS"]
topic = f"tinyd-ci-events-{uuid.uuid4().hex}"
group_id = f"tinyd-ci-{uuid.uuid4().hex}"
expected = "tenant-a|event-1|execution-1"
producer = KafkaProducer(
    bootstrap_servers=bootstrap,
    value_serializer=lambda value: value.encode(),
)
admin = KafkaAdminClient(bootstrap_servers=bootstrap, client_id=f"tinyd-ci-admin-{uuid.uuid4().hex}")
consumer = None

try:
    # Explicitly create the unique topic. partitions_for() only discovers
    # metadata; it does not create a topic and therefore cannot establish it.
    try:
        admin.create_topics([NewTopic(name=topic, num_partitions=1, replication_factor=1)])
    except TopicAlreadyExistsError:
        pass

    topic_ready_deadline = time.monotonic() + 10
    while producer.partitions_for(topic) != {0}:
        if time.monotonic() >= topic_ready_deadline:
            raise AssertionError(f"Kafka topic was not ready: {topic}")
        time.sleep(0.25)

    consumer = KafkaConsumer(
        bootstrap_servers=bootstrap,
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        group_id=group_id,
        value_deserializer=lambda value: value.decode(),
    )
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

    assert values == [expected], f"Kafka event mismatch: expected={[expected]!r}, values={values!r}"
finally:
    if consumer is not None:
        consumer.close()
    admin.close()
    producer.close()
