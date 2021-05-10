from __future__ import annotations

import datetime
import errno
import logging
import os
import socket
from random import randint
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from twisted.internet import ssl
from twisted.internet.defer import inlineCallbacks
from twisted.internet.endpoints import SSL4ServerEndpoint, TCP4ServerEndpoint
from twisted.web.proxy import ReverseProxyResource
from twisted.web.server import Site

from gridsync.types import TwistedDeferred

# pylint: disable=ungrouped-imports
if TYPE_CHECKING:
    from twisted.internet.interfaces import IReactorCore
    from twisted.web.server import Request

    from gridsync.tahoe import Tahoe  # pylint: disable=cyclic-import


def get_local_network_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    s.connect(("10.255.255.255", 1))
    ip = s.getsockname()[0]
    s.close()
    return ip


def get_free_port(
    port: int = 0, range_min: int = 49152, range_max: int = 65535
) -> int:
    if not port:
        port = randint(range_min, range_max)
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                logging.debug("Trying to bind to port: %i", port)
                s.bind(("127.0.0.1", port))
            except socket.error as err:
                logging.debug("Couldn't bind to port %i: %s", port, err)
                if err.errno == errno.EADDRINUSE:
                    port = randint(range_min, range_max)
                    continue
                raise
            logging.debug("Port %s is free", port)
            return port


def create_certificate(pemfile: str, common_name: str) -> bytes:
    key = ec.generate_private_key(ec.SECP256R1())
    subject = issuer = x509.Name(
        [x509.NameAttribute(x509.oid.NameOID.COMMON_NAME, common_name)]
    )
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.utcnow())
        .not_valid_after(
            datetime.datetime.utcnow() + datetime.timedelta(days=365 * 100)
        )
        .sign(key, hashes.SHA256())
    )
    with open(pemfile, "wb") as f:
        f.write(
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
            + cert.public_bytes(serialization.Encoding.PEM)
        )
    return cert.fingerprint(hashes.SHA256())


def get_certificate_digest(pemfile: str) -> bytes:
    with open(pemfile) as f:
        cert = x509.load_pem_x509_certificate(f.read().encode())
    digest = cert.fingerprint(hashes.SHA256())
    return digest


class BridgeReverseProxyResource(ReverseProxyResource):
    def __init__(  # pylint: disable=too-many-arguments
        self,
        bridge: Bridge,
        host: str,
        port: int,
        path: bytes,
        reactor: IReactorCore,
    ) -> None:
        self.bridge = bridge
        super().__init__(host, port, path, reactor)

    def getChild(self, path: bytes, request: Request) -> ReverseProxyResource:
        self.bridge.resource_requested(request)
        return super().getChild(path, request)


class Bridge:
    def __init__(
        self, gateway: Tahoe, reactor: IReactorCore, use_tls: bool = True
    ) -> None:
        self.gateway = gateway
        self._reactor = reactor
        self.use_tls = use_tls
        if use_tls:
            self.scheme = "https"
        else:
            self.scheme = "http"
        self.pemfile = os.path.join(gateway.nodedir, "private", "bridge.pem")
        self.urlfile = os.path.join(gateway.nodedir, "private", "bridge.url")
        self.proxy = None
        self.address = ""
        self.__certificate_digest: bytes = b""

    def get_certificate_digest(self) -> bytes:
        if not self.__certificate_digest:
            self.__certificate_digest = get_certificate_digest(self.pemfile)
        return self.__certificate_digest

    @inlineCallbacks
    def start(self, nodeurl: str, port: int = 0) -> TwistedDeferred[None]:
        if self.proxy and self.proxy.connected:
            logging.warning("Tried to start a bridge that was already running")
            return
        lan_ip = get_local_network_ip()
        if os.path.exists(self.urlfile):
            with open(self.urlfile) as f:
                url = urlparse(f.read().strip())
            lan_ip, port = url.hostname, url.port
            # TODO: Check that hostname matches lan_ip
        else:
            if not port:
                port = get_free_port()
            with open(self.urlfile, "w") as f:
                f.write(f"{self.scheme}://{lan_ip}:{port}")
        logging.debug(
            "Starting bridge: %s://%s:%s -> %s ...",
            self.scheme,
            lan_ip,
            port,
            nodeurl,
        )
        if self.use_tls:
            if not os.path.exists(self.pemfile):
                self.__certificate_digest = create_certificate(
                    self.pemfile, lan_ip + ".invalid"
                )
            with open(self.pemfile) as f:
                certificate = ssl.PrivateCertificate.loadPEM(
                    f.read()
                ).options()
            endpoint = SSL4ServerEndpoint(
                self._reactor, port, certificate, interface=lan_ip
            )
        else:
            endpoint = TCP4ServerEndpoint(  # type: ignore
                self._reactor, port, interface=lan_ip
            )
        url = urlparse(nodeurl)
        self.proxy = yield endpoint.listen(
            Site(
                BridgeReverseProxyResource(
                    self, url.hostname, url.port, b"", self._reactor
                )
            )
        )
        host = self.proxy.getHost()  # type: ignore
        self.address = f"{self.scheme}://{host.host}:{host.port}"
        if self.use_tls:
            d = iter(self.get_certificate_digest().hex().upper())
            fp = ":".join(a + b for a, b in zip(d, d))
            logging.debug(
                "Bridge started: %s (certificate digest: %s)", self.address, fp
            )
        else:
            logging.debug("Bridge started: %s", self.address)

    @staticmethod
    def resource_requested(request: Request) -> None:
        logging.debug(
            "%s %s %s", request.getClientIP(), request.method, request.uri
        )

    @inlineCallbacks
    def stop(self) -> TwistedDeferred[None]:
        if not self.proxy or not self.proxy.connected:
            logging.warning("Tried to stop a bridge that was not running")
            return
        host = self.proxy.getHost()
        logging.debug(
            "Stopping bridge: %s://%s:%s ...",
            self.scheme,
            host.host,
            host.port,
        )
        yield self.proxy.stopListening()
        logging.debug(
            "Bridge stopped: %s://%s:%s", self.scheme, host.host, host.port
        )
        self.proxy = None