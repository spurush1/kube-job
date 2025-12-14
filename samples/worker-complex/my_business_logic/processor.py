import time

class ComplexProcessor:
    def __init__(self):
        print("Initializing heavy models or database connections...")
        # self.model = load_model(...)

    def process(self, data):
        """
        Pure business logic. Knows nothing about RabbitMQ.
        """
        print(f"[Logic] Analysing complex data: {data}")
        time.sleep(1)
        return {"status": "success", "score": 99}
