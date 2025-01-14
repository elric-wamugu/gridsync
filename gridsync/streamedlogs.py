# -*- coding: utf-8 -*-

"""
Support for reading the streaming Eliot logs available from a Tahoe-LAFS
node.
"""

import logging
from collections import deque
from typing import Optional

from autobahn.twisted.websocket import (
    WebSocketClientFactory,
    WebSocketClientProtocol,
)
from hyperlink import parse
from twisted.application.internet import ClientService
from twisted.application.service import MultiService
from twisted.internet.endpoints import TCP4ClientEndpoint
from twisted.internet.interfaces import IReactorTime


class TahoeLogReader(
    WebSocketClientProtocol
):  # pylint: disable=too-many-ancestors
    def onMessage(self, payload: bytes, isBinary: bool) -> None:
        if isBinary:
            logging.warning(
                "Received a binary-mode WebSocket message from Tahoe-LAFS "
                "streaming log; dropping.",
            )
        else:
            self.factory.streamedlogs.add_message(payload)


class StreamedLogs(MultiService):
    """
    :ivar _reactor: A reactor that can connect using whatever transport the
        Tahoe-LAFS node requires (TCP, etc).

    :ivar deque _buffer: Bounded storage for the streamed messages.
    """

    _started = False

    def __init__(
        self, reactor: IReactorTime, maxlen: Optional[int] = None
    ) -> None:
        super().__init__()
        self._reactor = reactor
        self._client_service: Optional[ClientService] = None
        if maxlen is None:
            # This deque limit is based on average message size of 260 bytes
            # and a desire to limit maximum memory consumption here to around
            # 500 MiB.
            maxlen = 2000000
        self._buffer: deque = deque(maxlen=maxlen)

    def add_message(self, message: bytes) -> None:
        self._buffer.append(message)

    def start(self, nodeurl: str, api_token: str) -> None:
        """
        Start reading logs from the streaming log endpoint.

        :param str nodeurl: The root URL of the Tahoe-LAFS web API.
        :param str api_token: The secret Tahoe-LAFS API token.
        """
        if not self.running:
            self._client_service = self._create_client_service(
                nodeurl, api_token
            )
            self._client_service.setServiceParent(self)
            return super().startService()
        return None

    def stop(self) -> None:
        if self.running:
            self._client_service.disownServiceParent()  # type: ignore
            self._client_service = None
            return super().stopService()
        return None

    def get_streamed_log_messages(self) -> list:
        """
        :return list[str]: The messages currently in the message buffer.
        """
        return list(msg.decode("utf-8") for msg in list(self._buffer))

    def _create_client_service(
        self, nodeurl: str, api_token: str
    ) -> ClientService:
        url = parse(nodeurl)
        wsurl = url.replace(scheme="ws").child("private", "logs", "v1")

        factory = WebSocketClientFactory(
            url=wsurl.to_uri().to_text(),
            headers={
                "Authorization": "{} {}".format("tahoe-lafs", api_token),
            },
        )
        factory.protocol = TahoeLogReader
        factory.streamedlogs = self

        endpoint = TCP4ClientEndpoint(self._reactor, url.host, url.port)
        client_service = ClientService(endpoint, factory, clock=self._reactor)
        return client_service
