class FakeExchange:
    def __init__(self) -> None:
        self.publications: list[tuple[object, str, bool]] = []

    async def publish(
        self,
        message: object,
        routing_key: str,
        mandatory: bool,
    ) -> None:
        self.publications.append((message, routing_key, mandatory))


class FakeChannel:
    def __init__(self) -> None:
        self.exchange = FakeExchange()
        self.declarations: list[tuple[str, object, bool]] = []
        self.is_closed = False

    async def declare_exchange(
        self,
        name: str,
        exchange_type: object,
        durable: bool,
    ) -> FakeExchange:
        self.declarations.append((name, exchange_type, durable))
        return self.exchange

    async def close(self) -> None:
        self.is_closed = True


class FakeConnection:
    def __init__(self) -> None:
        self.channel_instance = FakeChannel()
        self.channel_options: dict[str, bool] = {}

    async def channel(
        self,
        publisher_confirms: bool,
        on_return_raises: bool,
    ) -> FakeChannel:
        self.channel_options = {
            "publisher_confirms": publisher_confirms,
            "on_return_raises": on_return_raises,
        }
        return self.channel_instance
