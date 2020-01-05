"""
Module responsible for the communication through sockets

"""

import sys
import os
import time

import sgtk


__author__ = "Diego Garcia Huerta"
__contact__ = "https://www.linkedin.com/in/diegogh/"


logger = sgtk.platform.get_logger(__name__)

# Unfortunately we need to patch the qt module from sgtk to
# include QtNetwork. There is no provision for it in the engine init,
# or by implementing qt_base...
__importer = sgtk.util.qt_importer.QtImporter()

import sgtk.platform.qt as qt

qt.QtNetwork = __importer.QtNetwork

from sgtk.platform.qt import QtGui, QtCore, QtNetwork

import sys
import time
import json
import uuid

import logging
from datetime import datetime


MAX_READ_RESPONSE_TIME = 10000
MAX_WRITE_RESPONSE_TIME = 10000
INT32_SIZE = 4


class QTcpSocketClient(QtCore.QObject):
    def __init__(self, parent=None, host=None, port=None):
        super(QTcpSocketClient, self).__init__()

        self._parent = parent
        self._host = host
        self._port = port
        self._block_size = 0

        self._callbacks = {}
        self.responses = {}
        self.awaiting_response = []

        self.connection = QtNetwork.QTcpSocket(self)
        self.connection.connected.connect(self._on_connected)
        self._buffer = None
        self._receiving = False

    def host(self):
        return self._host

    def port(self):
        return self._port

    def connection_status(self):
        return self.connection.state()

    def is_connected(self):
        return self.connection and (
            self.connection_status() == QtNetwork.QAbstractSocket.ConnectedState
        )

    def connect_to_host(self, host=None, port=None):
        if not host:
            host = self._host

        if not port:
            port = self._port

        logger.debug("Connecting to Server... %s %s " % (host, port))

        self._port = port
        self._host = host

        if self.is_connected():
            logger.warning(
                "Connection already existed , removing connection to %s %s "
                % (host, port)
            )
            self.connection.abort()

        st2 = time.time()
        self.connection.connectToHost(host, port)

        if not self.connection.waitForConnected(1500):
            et2 = time.time()
            logger.error(
                "Error connecting to the server | %s secs" % (et2 - st2)
            )
            return self.connection_status()
        else:
            et2 = time.time()
            logger.debug("Connected. %s secs" % (et2 - st2))

        result = self.connection_status()
        logger.debug("Server status: %s", result)

        commands = self.send_and_receive_command("DIR")
        logger.debug("commands: %s" % commands)

        return result

    def _on_readyRead(self):
        logger.warning("Ready to read")

    def _on_error(self):
        logger.debug("Error occurred: %s" % self.connection.errorString())

    def _on_bytes_written(self, bytes):
        logger.debug("Bytes written: %s" % bytes)

    def _on_state_changed(self, state):
        logger.debug("stateChanged: %s" % state)

    def _on_connected(self):
        logger.debug("On connected to server called.")
        logger.debug("Connection: %s" % self.connection)

        logger.debug("Setting up callbacks...")
        self.connection.setSocketOption(self.connection.LowDelayOption, 1)
        self.connection.setSocketOption(self.connection.KeepAliveOption, 1)

        self.connection.readyRead.connect(self._on_ready_read)
        self.connection.error.connect(self._on_error)
        self.connection.bytesWritten.connect(self._on_bytes_written)
        self.connection.stateChanged.connect(self._on_state_changed)

        logger.debug("Setting up callbacks... Done.")

    def _send(self, request):
        # make sure we are connected
        if self.connection.state() in (
            QtNetwork.QAbstractSocket.SocketState.UnconnectedState,
        ):
            self.connect_to_host()

        block = QtCore.QByteArray()

        outstr = QtCore.QDataStream(block, QtCore.QIODevice.WriteOnly)
        outstr.setVersion(QtCore.QDataStream.Qt_4_6)

        outstr.writeString(str(request))

        self.connection.write(block)

        if not self.connection.waitForBytesWritten(MAX_WRITE_RESPONSE_TIME):
            logger.error(
                "Could not write to socket: %s" % self.connection.errorString()
            )
        else:
            logger.debug("Sent data ok. %s" % self.connection.state())

    def _on_ready_read(self):
        if not self._receiving:
            self._receive()

    def _receive(self):
        logger.debug("Receiving data ... ")

        stream = QtCore.QDataStream(self.connection)
        stream.setVersion(QtCore.QDataStream.Qt_4_6)

        i = 0
        while self.connection.bytesAvailable() > 0:
            if (
                self._block_size == 0
                and self.connection.bytesAvailable() >= INT32_SIZE
            ) or (
                self._block_size > 0
                and self.connection.bytesAvailable() >= self._block_size
            ):
                self._block_size = stream.readInt32()
                # logger.debug(
                #     "Reading data size for request %s in queue: %s"
                #     % (i, self._block_size)
                # )

            if (
                self._block_size > 0
                and self.connection.bytesAvailable() >= self._block_size
            ):
                data = stream.readRawData(self._block_size)
                request = QtCore.QTextCodec.codecForMib(106).toUnicode(data)
                # logger.debug("About to process request %s in queue: %s" % (i, request))
                self._process_request(request)
                self._block_size = 0
                i += 1

        return None

    def _prepare_request(self, method, request_return=False, **kwargs):
        request_id = uuid.uuid4().hex

        request = json.dumps(
            {
                "jsonrpc": "2.0",
                "method": method,
                "params": kwargs,
                "request_return": request_return,
                "id": request_id,
            }
        )
        return request_id, request

    def _prepare_reply(self, request_id, result):
        reply = json.dumps(
            {
                "jsonrpc": "2.0",
                "result": result,
                "request_return": False,
                "id": request_id,
            }
        )
        return request_id, reply

    def _process_request(self, request):
        # make sure is a json like request
        try:
            command = json.loads(request)
        except ValueError as e:
            logger.warning("Ignoring request, not well formed. %s", request)
            return None

        request_id = command.get("id")

        if not request_id:
            logger.warning("Ignoring request, not well formed. %s", request)
            return None

        # if this is a result return it
        if "result" in command:
            self.responses[request_id] = command["result"]

        elif "method" in command:
            method = command.get("method")
            kwargs = command.get("params")

            # check if any callbacks are registered for this request
            if method in self._callbacks:
                result = self._callbacks[method](**kwargs)

                if result and command.get("request_return"):
                    self.send_reply(request_id, result)
                    logger.debug("Sent back result: %s." % result)
            else:
                logger.warning("Command not recognized: %s. Skipping." % method)
        elif "error" in command:
            logger.error(
                "Error occurred when requesting command. %s" % command["error"]
            )
        else:
            logger.debug(
                "Not a command, and not a message we were waiting answer for. %s"
                % request_id
            )

    def send_and_receive_command(self, method, **kwargs):
        QtGui.QApplication.processEvents()

        st = time.time()
        request_id, request = self._prepare_request(
            method, request_return=True, **kwargs
        )
        self._send(request)
        st1 = time.time()

        logger.debug("Sent request in %s secs: %s" % ((st1 - st), request))

        # receive
        logger.debug("Waiting to receive data...")

        result = None

        if self.connection.waitForReadyRead(MAX_READ_RESPONSE_TIME):
            st3 = time.time()
            self._receiving = True
            self._receive()
            self._receiving = False
            et3 = time.time()
            result = self.responses.get(request_id)
            logger.debug(
                "Received command. in %s secs | Result: %s"
                % ((et3 - st3), result)
            )
        else:
            logger.warning("Did not receive any data.")

        et = time.time()
        logger.debug("Done send and receive. %s" % (et - st))

        QtGui.QApplication.processEvents()
        return result

    def send_command(self, method, **kwargs):
        request_id, request = self._prepare_request(method, **kwargs)
        st = time.time()
        self._send(request)
        et = time.time()
        logger.debug("Sent command in %s secs: %s" % ((et - st), request))

    def send_reply(self, request_id, result):
        _, reply = self._prepare_reply(request_id, result)
        st = time.time()
        self._send(reply)
        et = time.time()
        logger.debug("Sent reply in %s secs: %s" % ((et - st), reply))

    def error(self, socketError):
        if socketError == QtNetwork.QAbstractSocket.RemoteHostClosedError:
            logger.error("Host closed the connection...")
        elif socketError == QtNetwork.QAbstractSocket.HostNotFoundError:
            logger.error(
                "The host was not found. Please check the host name and "
                "port settings."
            )
        elif socketError == QtNetwork.QAbstractSocket.ConnectionRefusedError:
            logger.error("The server is not up and running yet.")
        else:
            logger.error(
                "The following error occurred: %s."
                % self.connection.errorString()
            )

    def close(self):
        self.connection.abort()

    def register_callback(self, method, callback):
        self._callbacks[method] = callback


class Client(QtGui.QDialog):
    def __init__(self, parent=None):
        super(Client, self).__init__(parent)

        hostLabel = QtGui.QLabel("&Server name:")
        portLabel = QtGui.QLabel("S&erver port:")
        methodLabel = QtGui.QLabel("Method:")
        paramsLabel = QtGui.QLabel("Params:")

        self.hostLineEdit = QtGui.QLineEdit("127.0.0.1")
        self.portLineEdit = QtGui.QLineEdit("55893")
        self.portLineEdit.setValidator(QtGui.QIntValidator(1, 65535, self))
        self.paramsLineEdit = QtGui.QLineEdit("{}")
        self.methodCombo = QtGui.QComboBox()
        self.resultsTextEdit = QtGui.QTextEdit("")

        hostLabel.setBuddy(self.hostLineEdit)
        portLabel.setBuddy(self.portLineEdit)
        paramsLabel.setBuddy(self.paramsLineEdit)
        methodLabel.setBuddy(self.methodCombo)

        self.statusLabel = QtGui.QLabel("Ready.")

        self.sendCommandButton = QtGui.QPushButton("Send")
        self.sendCommandButton.setDefault(True)
        self.sendCommandButton.setEnabled(False)

        quitButton = QtGui.QPushButton("Quit")
        self.connectButton = QtGui.QPushButton("Connect")

        buttonBox = QtGui.QDialogButtonBox()

        buttonBox.addButton(
            self.connectButton, QtGui.QDialogButtonBox.ActionRole
        )
        buttonBox.addButton(
            self.sendCommandButton, QtGui.QDialogButtonBox.ActionRole
        )
        buttonBox.addButton(quitButton, QtGui.QDialogButtonBox.RejectRole)

        self.hostLineEdit.textChanged.connect(self.enablesendCommandButton)
        self.portLineEdit.textChanged.connect(self.enablesendCommandButton)
        self.sendCommandButton.clicked.connect(self.sendCommand)
        self.connectButton.clicked.connect(self.connect_to_host)
        quitButton.clicked.connect(self.close)

        mainLayout = QtGui.QGridLayout()
        mainLayout.addWidget(hostLabel, 0, 0)
        mainLayout.addWidget(self.hostLineEdit, 0, 1)

        mainLayout.addWidget(portLabel, 1, 0)
        mainLayout.addWidget(self.portLineEdit, 1, 1)

        mainLayout.addWidget(methodLabel, 2, 0)
        mainLayout.addWidget(self.methodCombo, 2, 1)

        mainLayout.addWidget(paramsLabel, 3, 0)
        mainLayout.addWidget(self.paramsLineEdit, 3, 1)

        mainLayout.addWidget(self.resultsTextEdit, 4, 1)

        mainLayout.addWidget(self.statusLabel, 5, 0, 1, 2)
        mainLayout.addWidget(buttonBox, 6, 0, 1, 2)
        self.setLayout(mainLayout)

        self.setWindowTitle("Toon Boom Harmony Engine Client")
        self.portLineEdit.setFocus()

        self.client = QTcpSocketClient(parent=self)

    def ping(self):
        return "PONG"

    def show_menu(self, clickedPosition):
        logger.debug(
            "Client | Request for SHOW MENU received!: %s" % clickedPosition
        )

    def connect_to_host(self):
        self.client.close()
        self.client.register_callback("PING", self.ping)
        self.client.register_callback("SHOW_MENU", self.show_menu)

        self.client.connect_to_host(
            self.hostLineEdit.text(), int(self.portLineEdit.text())
        )

        self.sendCommandButton.setEnabled(True)
        commands = self.client.send_and_receive_command("DIR")

        if commands:
            self.methodCombo.addItems(commands)
            self.client.send_command("ENGINE_READY")

    def sendCommand(self):
        data = self.paramsLineEdit.text()
        command = self.methodCombo.currentText()
        data = eval(data)

        if command == "SHOW_MENU" or command == "ENGINE_READY":
            self.client.send_command(command, **data)
        else:
            result = self.client.send_and_receive_command(command, **data)
            if result:
                self.resultsTextEdit.setText("%s" % result)

    def enablesendCommandButton(self):
        self.sendCommandButton.setEnabled(
            bool(self.hostLineEdit.text() and self.portLineEdit.text())
        )


if __name__ == "__main__":

    import sys

    logger.info("-" * 80)
    logger.info("--- external client ---")
    logger.info("-" * 80)
    app = QtGui.QApplication(sys.argv)
    client = Client()
    client.show()
    sys.exit(client.exec_())
