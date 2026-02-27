import sys
from dataclasses import dataclass
from datetime import datetime

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtNetwork import QAbstractSocket, QTcpSocket
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QRadioButton,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QScrollArea,
    QMessageBox,
)


# -----------------------------
# Packet Builders (Fixed-length, ASCII)
# -----------------------------
def now_14() -> str:
    # YYYYMMDDHHMMSS (14)
    return datetime.now().strftime("%Y%m%d%H%M%S")


def pad_right(s: str, n: int, ch: str = " ") -> str:
    s = "" if s is None else str(s)
    if len(s) > n:
        return s[:n]
    return s + (ch * (n - len(s)))


def pad_left(s: str, n: int, ch: str = "0") -> str:
    s = "" if s is None else str(s)
    if len(s) > n:
        return s[-n:]
    return (ch * (n - len(s))) + s


@dataclass
class Alive1199:
    count: int
    work_a: str = "01"  # "01" 정상, "99" 비정상
    work_b: str = "01"

    def build(self) -> str:
        tc = "1199"
        cdate = now_14()
        length = "000052"
        ccnt = pad_left(self.count, 4, "0")
        work_a = pad_right(self.work_a, 2, "0")[:2]
        work_b = pad_right(self.work_b, 2, "0")[:2]
        spare = pad_right("", 20, " ")
        msg = tc + cdate + length + ccnt + work_a + work_b + spare
        # Safety check
        if len(msg) != 52:
            raise ValueError(f"Alive1199 length mismatch: {len(msg)}")
        return msg


@dataclass
class Winding1101:
    bundle: str
    mtrl: str
    line: str  # "A" or "B"
    layer_states_25: list  # 25 chars, each in {"N","T","H","U"}

    def build(self) -> str:
        tc = "1101"
        cdate = now_14()
        length = "000072"
        bundle = pad_right(self.bundle, 10, " ")
        mtrl = pad_right(self.mtrl, 10, " ")
        line = (self.line or "A")[:1]
        layer_count = "25"  # UI가 25개 고정이므로 25로 송신
        layers = "".join((s or "N")[:1] for s in self.layer_states_25)
        layers = pad_right(layers, 25, "N")[:25]

        msg = tc + cdate + length + bundle + mtrl + line + layer_count + layers
        if len(msg) != 72:
            raise ValueError(f"Winding1101 length mismatch: {len(msg)}")
        return msg


@dataclass
class ResultChange1010:
    bundle: str
    mtrl: str
    line: str
    filenames_10: list  # up to 10, each <=50

    def build(self) -> str:
        tc = "1010"
        cdate = now_14()
        length = "000576"
        bundle = pad_right(self.bundle, 10, " ")
        mtrl = pad_right(self.mtrl, 10, " ")
        line = (self.line or "A")[:1]

        files = ""
        for i in range(10):
            fn = ""
            if i < len(self.filenames_10):
                fn = self.filenames_10[i] or ""
            files += pad_right(fn, 50, " ")[:50]

        spare = pad_right("", 31, " ")
        msg = tc + cdate + length + bundle + mtrl + line + files + spare
        if len(msg) != 576:
            raise ValueError(f"ResultChange1010 length mismatch: {len(msg)}")
        return msg


# -----------------------------
# UI Widgets
# -----------------------------
class LayerStateRow(QWidget):
    """
    요구는 '체크박스 4개'이지만, 실무상 레이어당 상태는 1개만 선택이 자연스러워서
    UI는 체크박스처럼 보이는 단일선택(라디오)로 구현합니다.
    """
    def __init__(self, layer_idx_1based: int, parent=None):
        super().__init__(parent)
        self.layer_idx = layer_idx_1based

        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)

        lbl = QLabel(f"L{layer_idx_1based:02d}")
        lbl.setFixedWidth(40)
        layout.addWidget(lbl)

        self.group = QButtonGroup(self)
        self.group.setExclusive(True)

        self.rb_n = QRadioButton("N")
        self.rb_t = QRadioButton("T")
        self.rb_h = QRadioButton("H")
        self.rb_u = QRadioButton("U")

        # Default: N
        self.rb_n.setChecked(True)

        for rb in (self.rb_n, self.rb_t, self.rb_h, self.rb_u):
            self.group.addButton(rb)
            layout.addWidget(rb)

        layout.addStretch(1)

    def get_state(self) -> str:
        if self.rb_n.isChecked():
            return "N"
        if self.rb_t.isChecked():
            return "T"
        if self.rb_h.isChecked():
            return "H"
        if self.rb_u.isChecked():
            return "U"
        return "N"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LV2 Protocol Test Client (PyQt6)")
        self.resize(1100, 820)

        self.socket = QTcpSocket(self)
        self.socket.connected.connect(self.on_connected)
        self.socket.disconnected.connect(self.on_disconnected)
        self.socket.readyRead.connect(self.on_ready_read)
        self.socket.errorOccurred.connect(self.on_error)

        self.alive_counter = 1

        # Alive timer: 30 sec
        self.alive_timer = QTimer(self)
        self.alive_timer.setInterval(30_000)
        self.alive_timer.timeout.connect(self.on_alive_timer)

        root = QWidget()
        self.setCentralWidget(root)
        main_layout = QVBoxLayout(root)

        # Connection box
        conn_box = QGroupBox("Connection")
        conn_layout = QGridLayout(conn_box)

        self.ip_edit = QLineEdit()
        self.ip_edit.setPlaceholderText("IP (e.g., 192.168.0.10)")
        self.port_edit = QLineEdit()
        self.port_edit.setPlaceholderText("Port (e.g., 5000)")

        self.btn_connect = QPushButton("Connect")
        self.btn_disconnect = QPushButton("Disconnect")
        self.btn_disconnect.setEnabled(False)

        self.btn_connect.clicked.connect(self.connect_to_server)
        self.btn_disconnect.clicked.connect(self.disconnect_from_server)

        conn_layout.addWidget(QLabel("IP"), 0, 0)
        conn_layout.addWidget(self.ip_edit, 0, 1)
        conn_layout.addWidget(QLabel("Port"), 0, 2)
        conn_layout.addWidget(self.port_edit, 0, 3)
        conn_layout.addWidget(self.btn_connect, 0, 4)
        conn_layout.addWidget(self.btn_disconnect, 0, 5)

        # Alive controls
        self.chk_alive_enable = QCheckBox("Enable Alive (send every 30s)")
        self.chk_alive_enable.setChecked(False)

        self.work_a_combo = QComboBox()
        self.work_a_combo.addItems(["01 (OK)", "99 (NG)"])
        self.work_b_combo = QComboBox()
        self.work_b_combo.addItems(["01 (OK)", "99 (NG)"])

        conn_layout.addWidget(self.chk_alive_enable, 1, 0, 1, 2)
        conn_layout.addWidget(QLabel("WORK_A"), 1, 2)
        conn_layout.addWidget(self.work_a_combo, 1, 3)
        conn_layout.addWidget(QLabel("WORK_B"), 1, 4)
        conn_layout.addWidget(self.work_b_combo, 1, 5)

        main_layout.addWidget(conn_box)

        # Winding Status 1101
        self.winding_box = QGroupBox("1101 Winding Status")
        winding_layout = QVBoxLayout(self.winding_box)

        top_row = QHBoxLayout()
        self.w_bundle = QLineEdit()
        self.w_bundle.setPlaceholderText("Bundle No (10 chars)")
        self.w_mtrl = QLineEdit()
        self.w_mtrl.setPlaceholderText("MTRL No (10 chars)")

        self.w_line_group = QButtonGroup(self)
        self.w_line_a = QRadioButton("Line A")
        self.w_line_b = QRadioButton("Line B")
        self.w_line_a.setChecked(True)
        self.w_line_group.addButton(self.w_line_a)
        self.w_line_group.addButton(self.w_line_b)

        top_row.addWidget(QLabel("Bundle"))
        top_row.addWidget(self.w_bundle)
        top_row.addWidget(QLabel("MTRL"))
        top_row.addWidget(self.w_mtrl)
        top_row.addWidget(self.w_line_a)
        top_row.addWidget(self.w_line_b)

        self.btn_send_1101 = QPushButton("Send 1101")
        self.btn_send_1101.clicked.connect(self.send_1101)

        top_row.addWidget(self.btn_send_1101)
        winding_layout.addLayout(top_row)

        # Layer controls (scroll)
        layers_container = QWidget()
        layers_grid = QGridLayout(layers_container)
        layers_grid.setContentsMargins(6, 6, 6, 6)
        layers_grid.setHorizontalSpacing(10)
        layers_grid.setVerticalSpacing(2)

        self.layer_rows = []
        # 25 rows, arrange 2 columns for compactness
        for i in range(25):
            row_widget = LayerStateRow(i + 1)
            self.layer_rows.append(row_widget)
            r = i % 13
            c = 0 if i < 13 else 1
            layers_grid.addWidget(row_widget, r, c)

        layers_scroll = QScrollArea()
        layers_scroll.setWidgetResizable(True)
        layers_scroll.setWidget(layers_container)

        winding_layout.addWidget(layers_scroll)
        main_layout.addWidget(self.winding_box, stretch=2)

        # Result Change 1010
        self.result_box = QGroupBox("1010 Result Change")
        result_layout = QVBoxLayout(self.result_box)

        r_top = QHBoxLayout()
        self.r_bundle = QLineEdit()
        self.r_bundle.setPlaceholderText("Bundle No (10 chars)")
        self.r_mtrl = QLineEdit()
        self.r_mtrl.setPlaceholderText("MTRL No (10 chars)")

        self.r_line_group = QButtonGroup(self)
        self.r_line_a = QRadioButton("Line A")
        self.r_line_b = QRadioButton("Line B")
        self.r_line_a.setChecked(True)
        self.r_line_group.addButton(self.r_line_a)
        self.r_line_group.addButton(self.r_line_b)

        self.btn_send_1010 = QPushButton("Send 1010")
        self.btn_send_1010.clicked.connect(self.send_1010)

        r_top.addWidget(QLabel("Bundle"))
        r_top.addWidget(self.r_bundle)
        r_top.addWidget(QLabel("MTRL"))
        r_top.addWidget(self.r_mtrl)
        r_top.addWidget(self.r_line_a)
        r_top.addWidget(self.r_line_b)
        r_top.addWidget(self.btn_send_1010)

        result_layout.addLayout(r_top)

        # 10 filenames
        fn_grid = QGridLayout()
        self.fn_edits = []
        for i in range(10):
            lbl = QLabel(f"FileName {i+1}")
            edit = QLineEdit()
            edit.setPlaceholderText("<= 50 chars (e.g., 20251230150001_C300ZZ_..._1_N.jpg)")
            self.fn_edits.append(edit)
            fn_grid.addWidget(lbl, i // 2, (i % 2) * 2)
            fn_grid.addWidget(edit, i // 2, (i % 2) * 2 + 1)

        result_layout.addLayout(fn_grid)
        main_layout.addWidget(self.result_box, stretch=1)

        # Log
        self.log = QTextEdit()
        self.log.setReadOnly(False)
        main_layout.addWidget(QGroupBox("Log"), stretch=0)
        main_layout.addWidget(self.log, stretch=1)

        self.log_line("UI ready.")

    # -----------------------------
    # Connection handlers
    # -----------------------------
    def connect_to_server(self):
        ip = self.ip_edit.text().strip()
        port_str = self.port_edit.text().strip()
        if not ip or not port_str:
            QMessageBox.warning(self, "Input Error", "IP와 Port를 입력해 주십시오.")
            return
        try:
            port = int(port_str)
        except ValueError:
            QMessageBox.warning(self, "Input Error", "Port는 정수여야 합니다.")
            return

        if self.socket.state() in (QAbstractSocket.SocketState.ConnectingState, QAbstractSocket.SocketState.ConnectedState):
            self.log_line("Already connecting/connected.")
            return

        self.log_line(f"Connecting to {ip}:{port} ...")
        self.socket.connectToHost(ip, port)

    def disconnect_from_server(self):
        if self.socket.state() == QAbstractSocket.SocketState.ConnectedState:
            self.log_line("Disconnect requested.")
            self.socket.disconnectFromHost()
        else:
            self.log_line("Not connected.")

    def on_connected(self):
        self.log_line("Connected.")
        self.btn_connect.setEnabled(False)
        self.btn_disconnect.setEnabled(True)
        # Start alive timer regardless; it will only send if checkbox is checked
        if not self.alive_timer.isActive():
            self.alive_timer.start()

    def on_disconnected(self):
        self.log_line("Disconnected.")
        self.btn_connect.setEnabled(True)
        self.btn_disconnect.setEnabled(False)

    def on_error(self, socket_error):
        # socket_error is QAbstractSocket.SocketError
        self.log_line(f"Socket error: {self.socket.errorString()}")

    def on_ready_read(self):
        data = bytes(self.socket.readAll())
        # raw logging (ASCII safe)
        try:
            text = data.decode("ascii", errors="replace")
        except Exception:
            text = repr(data)

        tc = text[:4] if len(text) >= 4 else "????"
        self.log_line(f"RX ({len(data)} bytes) TC={tc}: {text}")

    # -----------------------------
    # Alive timer
    # -----------------------------
    def on_alive_timer(self):
        if not self.chk_alive_enable.isChecked():
            return
        if self.socket.state() != QAbstractSocket.SocketState.ConnectedState:
            return

        work_a = "01" if self.work_a_combo.currentIndex() == 0 else "99"
        work_b = "01" if self.work_b_combo.currentIndex() == 0 else "99"

        try:
            pkt = Alive1199(count=self.alive_counter, work_a=work_a, work_b=work_b).build()
            self.alive_counter += 1
            self.send_packet(pkt, tag="TX Alive1199")
        except Exception as e:
            self.log_line(f"Alive build/send failed: {e}")

    # -----------------------------
    # Send buttons
    # -----------------------------
    def send_1101(self):
        if self.socket.state() != QAbstractSocket.SocketState.ConnectedState:
            QMessageBox.warning(self, "Not Connected", "서버에 먼저 접속해 주십시오.")
            return

        bundle = self.w_bundle.text()
        mtrl = self.w_mtrl.text()
        line = "A" if self.w_line_a.isChecked() else "B"
        layers = [row.get_state() for row in self.layer_rows]

        try:
            pkt = Winding1101(bundle=bundle, mtrl=mtrl, line=line, layer_states_25=layers).build()
            self.send_packet(pkt, tag="TX 1101")
        except Exception as e:
            self.log_line(f"1101 build/send failed: {e}")
            QMessageBox.critical(self, "1101 Error", str(e))

    def send_1010(self):
        if self.socket.state() != QAbstractSocket.SocketState.ConnectedState:
            QMessageBox.warning(self, "Not Connected", "서버에 먼저 접속해 주십시오.")
            return

        bundle = self.r_bundle.text()
        mtrl = self.r_mtrl.text()
        line = "A" if self.r_line_a.isChecked() else "B"
        filenames = [e.text() for e in self.fn_edits]

        try:
            pkt = ResultChange1010(bundle=bundle, mtrl=mtrl, line=line, filenames_10=filenames).build()
            self.send_packet(pkt, tag="TX 1010")
        except Exception as e:
            self.log_line(f"1010 build/send failed: {e}")
            QMessageBox.critical(self, "1010 Error", str(e))

    # -----------------------------
    # Low-level send + log
    # -----------------------------
    def send_packet(self, pkt_ascii: str, tag: str = "TX"):
        b = pkt_ascii.encode("ascii", errors="strict")
        written = self.socket.write(b)
        self.socket.flush()

        tc = pkt_ascii[:4] if len(pkt_ascii) >= 4 else "????"
        self.log_line(f"{tag} ({len(b)} bytes, write={written}) TC={tc}: {pkt_ascii}")

    def log_line(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log.append(f"[{ts}] {msg}")


def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
