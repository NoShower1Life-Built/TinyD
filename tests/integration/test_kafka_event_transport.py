import os
import time
from kafka import KafkaConsumer, KafkaProducer

bootstrap = os.environ["KAFKA_BOOTSTRAP_SERVERS"]
topic = "tinyd-ci-events"
producer = KafkaProducer(bootstrap_servers=bootstrap, value_serializer=lambda value: value.encode())
producer.send(topic, value="tenant-a|event-1|execution-1").get(timeout=10)
producer.flush(timeout=10)
consumer = KafkaConsumer(topic, bootstrap_servers=bootstrap, auto_offset_reset="earliest", consumer_timeout_ms=10000, group_id=f"tinyd-ci-{time.time_ns()}", value_deserializer=lambda value: value.decode())
try:
    values = [message.value for message in consumer]
finally:
    consumer.close()
producer.close()
assert "tenant-a|event-1|execution-1" in values
