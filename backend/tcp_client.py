"""SPL TCP Client — L2 서버에 접속하는 SPL 클라이언트

L2 서버에 TCP 클라이언트로 접속하여:
  - Alive(1199) 30초 주기 발신
  - L2로부터 1001, 1002, 1010, 1099 수신 & 파싱
  - 소재정보(1002) 수신 시 자동 권취 시작
  - 1101 권취상태 발신
"""

import asyncio
import ftplib
import glob
import logging
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from backend.protocol import (
    TC_LENGTHS, TC_PARSERS,
    TC1001_Setup, TC1002_Material, TC1010_ResultChange,
    TC1099_Alive, TC1101_WindingStatus, TC1199_Alive,
)
from backend.data_store import DataStore, ConnectionState
from backend.ws_manager import WebSocketManager

logger = logging.getLogger(__name__)


class SPLTCPClient:
    def __init__(self, data_store: DataStore, ws_manager: WebSocketManager,
                 host: str = "127.0.0.1", port: int = 12147,
                 image_dir: str = "",
                 ftp_host: str = "", ftp_user: str = "",
                 ftp_pass: str = "", ftp_dir: str = ""):
        self.host = host
        self.port = port
        self.data_store = data_store
        self.ws_manager = ws_manager
        self.image_dir = image_dir

        # FTP 설정
        self.ftp_host = ftp_host
        self.ftp_user = ftp_user
        self.ftp_pass = ftp_pass
        self.ftp_dir = ftp_dir
        self.ftp_enabled = bool(ftp_host and image_dir)

        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None

        self.alive_counter = 0
        self.alive_paused = False
        self._alive_task: Optional[asyncio.Task] = None
        self._receive_task: Optional[asyncio.Task] = None
        self._alive_watchdog_task: Optional[asyncio.Task] = None
        self._reconnect_task: Optional[asyncio.Task] = None
        self._last_alive_rx: Optional[float] = None
        self._running = False

        # 자동 권취
        self._auto_winding_task: Optional[asyncio.Task] = None
        self._winding_layers: list = []
        self.auto_winding_layers: list = ["N"] * 25   # 자동 권취 레이어 상태 (25개)
        self.auto_winding_layer_count: int = 25        # 자동 권취 레이어 개수

    async def start(self):
        """시작: L2 서버에 접속 시도"""
        self._running = True
        self._reconnect_task = asyncio.create_task(self._connect_loop())

    async def stop(self):
        """정지"""
        self._running = False
        for task in [self._alive_task, self._receive_task,
                     self._alive_watchdog_task, self._reconnect_task,
                     self._auto_winding_task]:
            if task:
                task.cancel()
        if self.writer:
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except Exception:
                pass
        logger.info("SPL TCP Client stopped")

    async def _connect_loop(self):
        """자동 재접속 루프"""
        while self._running:
            if not self.writer:
                try:
                    await self._connect()
                except (ConnectionRefusedError, OSError) as e:
                    logger.warning(f"L2 접속 실패: {e} (5초 후 재시도)")
                    await asyncio.sleep(5)
                    continue
                except asyncio.CancelledError:
                    return
            await asyncio.sleep(1)

    async def _connect(self):
        """L2 서버에 접속"""
        self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
        logger.info(f"L2 서버 접속 성공: {self.host}:{self.port}")

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.data_store.connection_state = ConnectionState.CONNECTED
        self.data_store.l2_connected_since = now

        self._last_alive_rx = asyncio.get_event_loop().time()

        await self.ws_manager.broadcast("connection_changed", {
            "state": ConnectionState.CONNECTED.value,
            "timestamp": now,
        })

        # Alive 발신 루프 (1199)
        if self._alive_task:
            self._alive_task.cancel()
        self._alive_task = asyncio.create_task(self._alive_send_loop())

        # Alive 감시
        if self._alive_watchdog_task:
            self._alive_watchdog_task.cancel()
        self._alive_watchdog_task = asyncio.create_task(self._alive_watchdog())

        # 수신 루프
        try:
            await self._receive_loop()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Receive loop error: {e}")
        finally:
            await self._on_disconnected()

    async def _receive_loop(self):
        """TCP 스트림에서 전문 단위 파싱 루프"""
        while self._running and self.reader:
            try:
                tc_bytes = await self.reader.readexactly(4)
            except (asyncio.IncompleteReadError, ConnectionError):
                logger.info("L2 연결 끊김 감지")
                return

            tc_code = tc_bytes.decode("ascii", errors="replace")

            total_len = TC_LENGTHS.get(tc_code)
            if total_len is None:
                logger.warning(f"Unknown TC code: {tc_code}")
                continue

            try:
                remaining = await self.reader.readexactly(total_len - 4)
            except (asyncio.IncompleteReadError, ConnectionError):
                logger.info("L2 연결 끊김 (수신 중)")
                return

            full_msg = tc_bytes.decode("ascii") + remaining.decode("ascii", errors="replace")
            await self._dispatch(tc_code, full_msg)

    async def _dispatch(self, tc_code: str, raw: str):
        """수신 전문 라우팅"""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        parsed_data = {}

        try:
            parser = TC_PARSERS.get(tc_code)
            if parser:
                parsed_obj = parser(raw)
                parsed_data = self._obj_to_dict(parsed_obj)
        except Exception as e:
            logger.error(f"Parse error TC {tc_code}: {e}")

        self.data_store.add_packet_log("RX", tc_code, raw, parsed_data)
        await self.ws_manager.broadcast("packet_log", {
            "direction": "RX", "tc": tc_code, "raw": raw,
            "parsed": parsed_data, "timestamp": now_str,
        })

        if tc_code == "1001":
            await self._handle_setup(raw, parsed_data)
        elif tc_code == "1002":
            await self._handle_material(raw, parsed_data)
        elif tc_code == "1010":
            await self._handle_result_change(raw, parsed_data)
        elif tc_code == "1099":
            await self._handle_alive_rx(raw, parsed_data)
        else:
            logger.info(f"RX TC={tc_code} ({len(raw)}B)")

    async def _handle_setup(self, raw: str, parsed: dict):
        """TC 1001 생산정보 수신 (L2→SPL)"""
        try:
            obj = TC1001_Setup.parse(raw)
            self.data_store.current_setup = obj
            await self.ws_manager.broadcast("setup_received", parsed)
            logger.info(f"RX TC=1001 dims={obj.dims_name} grade={obj.mat_grade}")
        except Exception as e:
            logger.error(f"Handle setup error: {e}")

    async def _handle_material(self, raw: str, parsed: dict):
        """TC 1002 소재정보 수신 (L2→SPL) → 자동 권취 트리거"""
        try:
            obj = TC1002_Material.parse(raw)
            self.data_store.current_material = obj
            self.data_store.update_coil_from_material(obj)

            await self.ws_manager.broadcast("material_received", parsed)
            logger.info(f"RX TC=1002 bundle={obj.bundle_no} line={obj.line_no}")

            # 자동 권취가 활성화되어 있으면 시작
            if self.data_store.auto_winding_enabled:
                await self.start_auto_winding(obj)
        except Exception as e:
            logger.error(f"Handle material error: {e}")

    async def _handle_result_change(self, raw: str, parsed: dict):
        """TC 1010 판정결과 변경 수신 (L2→SPL) → 파일명 변경"""
        try:
            obj = TC1010_ResultChange.parse(raw)
            self.data_store.current_result_change = obj
            await self.ws_manager.broadcast("result_change_received", parsed)
            logger.info(f"RX TC=1010 bundle={obj.bundle_no}")

            # 파일명 변경 처리
            if self.image_dir:
                rename_results = await self._rename_files_for_result_change(obj)
                if rename_results:
                    await self.ws_manager.broadcast("file_renamed", {
                        "bundle_no": obj.bundle_no,
                        "results": rename_results,
                    })
        except Exception as e:
            logger.error(f"Handle result change error: {e}")

    async def _rename_files_for_result_change(self, obj: TC1010_ResultChange) -> list:
        """1010 수신 파일명 목록에 맞춰 image_dir 내 파일 리네임.

        파일명 형식: YYYYMMDDHHMMSS_BUNDLE_MTRL_LINE_LNN_STATUS[.ext]
        매칭 기준: 마지막 '_' 앞 부분(prefix)이 동일한 파일을 찾아 리네임.
        L2에서 확장자 없이 보내는 경우 기존 파일의 확장자를 보존한다.

        예) 1010에 `20260303141020_S78588B031_S78588069_A_L03_T` 수신 (확장자 없음)
            → 기존 `20260303141020_S78588B031_S78588069_A_L03_N.jpg` 를 찾아서
            → `20260303141020_S78588B031_S78588069_A_L03_T.jpg` 로 리네임 (확장자 보존)
        """
        results = []
        img_dir = Path(self.image_dir)
        if not img_dir.is_dir():
            logger.warning(f"Image dir not found: {self.image_dir}")
            return results

        for new_filename in obj.filenames:
            new_filename = new_filename.strip()
            if not new_filename:
                continue

            # 확장자 분리
            has_ext = '.' in new_filename
            if has_ext:
                name_part, _, ext = new_filename.rpartition('.')
            else:
                name_part = new_filename
                ext = ""

            # 마지막 '_' 기준으로 prefix 추출 (STATUS 앞까지)
            # 예: "20260303141020_S78588B031_S78588069_A_L03_T" → prefix="...L03", new_status="T"
            prefix, _, new_status = name_part.rpartition('_')
            if not prefix:
                logger.warning(f"Cannot parse filename: {new_filename}")
                results.append({"new": new_filename, "old": "", "status": "parse_error"})
                continue

            # 기존 파일 검색: prefix_* (확장자 무관하게 검색)
            pattern = str(img_dir / f"{prefix}_*")
            matches = glob.glob(pattern)

            if not matches:
                logger.info(f"[RENAME] No match for {new_filename}")
                results.append({"new": new_filename, "old": "", "status": "not_found"})
                continue

            # 정확히 prefix_STATUS[.ext] 형태만 필터
            exact_matches = []
            for m in matches:
                m_basename = os.path.basename(m)
                m_name = m_basename.rsplit('.', 1)[0] if '.' in m_basename else m_basename
                m_prefix, _, m_status = m_name.rpartition('_')
                if m_prefix == prefix and m_status != new_status:
                    exact_matches.append(m)

            if not exact_matches:
                # 이미 동일한 상태 확인
                already_matches = []
                for m in matches:
                    m_basename = os.path.basename(m)
                    m_name = m_basename.rsplit('.', 1)[0] if '.' in m_basename else m_basename
                    m_prefix, _, m_status = m_name.rpartition('_')
                    if m_prefix == prefix and m_status == new_status:
                        already_matches.append(m)
                if already_matches:
                    already_name = os.path.basename(already_matches[0])
                    logger.info(f"[RENAME] Already correct: {already_name}")
                    results.append({"new": already_name, "old": already_name, "status": "already_exists"})
                else:
                    logger.info(f"[RENAME] No status-different match for {new_filename}")
                    results.append({"new": new_filename, "old": "", "status": "not_found"})
                continue

            old_path = exact_matches[0]
            old_basename = os.path.basename(old_path)

            # 새 파일명 결정: L2가 확장자 없이 보낸 경우 기존 파일 확장자 보존
            if not has_ext and '.' in old_basename:
                old_ext = old_basename.rsplit('.', 1)[1]
                final_new_name = f"{prefix}_{new_status}.{old_ext}"
            else:
                final_new_name = new_filename

            new_path = img_dir / final_new_name

            try:
                os.rename(old_path, new_path)
                logger.info(f"[RENAME] {old_basename} → {final_new_name}")
                results.append({"new": final_new_name, "old": old_basename, "status": "ok"})
            except OSError as e:
                logger.error(f"[RENAME] Failed {old_basename} → {final_new_name}: {e}")
                results.append({"new": final_new_name, "old": old_basename, "status": f"error: {e}"})

        return results

    async def _handle_alive_rx(self, raw: str, parsed: dict):
        """TC 1099 L2 Alive 수신"""
        try:
            obj = TC1099_Alive.parse(raw)
            self._last_alive_rx = asyncio.get_event_loop().time()
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            self.data_store.alive_count_rx = int(obj.count)
            self.data_store.last_alive_rx_time = now_str

            if self.data_store.connection_state != ConnectionState.ALIVE_OK:
                self.data_store.connection_state = ConnectionState.ALIVE_OK
                await self.ws_manager.broadcast("connection_changed", {
                    "state": ConnectionState.ALIVE_OK.value,
                    "timestamp": now_str,
                })

            await self.ws_manager.broadcast("alive_received", {
                "direction": "RX",
                "count": obj.count,
                "timestamp": now_str,
            })
            logger.debug(f"RX TC=1099 cnt={obj.count}")
        except Exception as e:
            logger.error(f"Handle alive RX error: {e}")

    async def _alive_send_loop(self):
        """30초 주기 TC 1199 Alive 발신"""
        try:
            while self._running and self.writer:
                await asyncio.sleep(30)
                if not self.writer:
                    break
                if self.alive_paused:
                    continue
                self.alive_counter = (self.alive_counter + 1) % 10000
                pkt = TC1199_Alive(
                    count=self.alive_counter,
                    work_a=self.data_store.work_a,
                    work_b=self.data_store.work_b,
                )
                await self.send_packet(pkt.build(), "1199")
                self.data_store.alive_count_tx = self.alive_counter
        except asyncio.CancelledError:
            pass

    async def _alive_watchdog(self):
        """L2 Alive(1099) 수신 감시: 90초 타임아웃"""
        try:
            while self._running:
                await asyncio.sleep(10)
                if self._last_alive_rx is None:
                    continue
                elapsed = asyncio.get_event_loop().time() - self._last_alive_rx
                if elapsed > 90:
                    if self.data_store.connection_state != ConnectionState.ALIVE_TIMEOUT:
                        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        self.data_store.connection_state = ConnectionState.ALIVE_TIMEOUT
                        await self.ws_manager.broadcast("connection_changed", {
                            "state": ConnectionState.ALIVE_TIMEOUT.value,
                            "timestamp": now_str,
                        })
                        logger.warning("L2 Alive timeout (>90s)")
        except asyncio.CancelledError:
            pass

    async def send_packet(self, raw: str, tc_code: str = None):
        """TCP로 전문 전송"""
        if not self.writer:
            logger.warning("Cannot send: L2 미접속")
            return False

        try:
            self.writer.write(raw.encode("ascii"))
            await self.writer.drain()
        except Exception as e:
            logger.error(f"Send error: {e}")
            return False

        if tc_code is None:
            tc_code = raw[0:4] if len(raw) >= 4 else "????"

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        parsed_data = {}
        try:
            parser = TC_PARSERS.get(tc_code)
            if parser:
                parsed_data = self._obj_to_dict(parser(raw))
        except Exception:
            pass

        self.data_store.add_packet_log("TX", tc_code, raw, parsed_data)
        await self.ws_manager.broadcast("packet_log", {
            "direction": "TX", "tc": tc_code, "raw": raw,
            "parsed": parsed_data, "timestamp": now_str,
        })
        logger.debug(f"TX TC={tc_code} ({len(raw)}B)")
        return True

    async def send_winding_status(self, bundle_no, mtrl_no, line_no, layer_count, layers, date=""):
        """TC 1101 권취상태 전송 + seed 이미지 생성 & FTP 업로드"""
        pkt = TC1101_WindingStatus(
            bundle_no=bundle_no,
            mtrl_no=mtrl_no,
            line_no=line_no,
            layer_count=layer_count,
            layers=layers,
            date=date,
        )
        raw = pkt.build()
        success = await self.send_packet(raw, "1101")

        if success:
            self.data_store.update_winding(bundle_no, mtrl_no, line_no, layer_count, layers)
            await self.ws_manager.broadcast("winding_status", {
                "bundle_no": bundle_no,
                "mtrl_no": mtrl_no,
                "line_no": line_no,
                "layer_count": layer_count,
                "layers": [
                    {"index": i + 1, "status": layers[i]}
                    for i in range(25)
                ],
            })

            # seed 이미지 복사 + FTP 업로드
            if self.ftp_enabled:
                # 1101 헤더의 Date 필드 (14자리) — date 파라미터가 비어있으면 현재시각
                pkt_date = date if date else datetime.now().strftime("%Y%m%d%H%M%S")
                ftp_results = await self._generate_and_upload_images(
                    pkt_date, bundle_no, mtrl_no, line_no, layer_count, layers
                )
                if ftp_results:
                    await self.ws_manager.broadcast("ftp_upload_result", {
                        "bundle_no": bundle_no,
                        "results": ftp_results,
                    })

        return success

    async def _generate_and_upload_images(
        self, date_str: str, bundle_no: str, mtrl_no: str,
        line_no: str, layer_count: int, layers: list
    ) -> list:
        """seed.jpg를 복사/리네임하여 FTP 서버에 업로드

        파일명 형식: {date}_{bundle}_{mtrl}_{line}_L{nn}_{status}.jpg
        seed 파일: {image_dir}/seed.jpg
        임시 디렉토리에 생성 후 FTP 업로드, 완료 후 img_dir로 이동.
        """
        img_dir = Path(self.image_dir)
        seed_path = img_dir / "seed.jpg"

        if not seed_path.is_file():
            logger.warning(f"[FTP] Seed file not found: {seed_path}")
            return [{"filename": "seed.jpg", "status": "seed_not_found"}]

        # 임시 디렉토리에 25개 레이어 파일 생성 (파일 잠금 방지)
        tmp_dir = Path(tempfile.mkdtemp(prefix="spl_ftp_"))
        generated_files = []
        try:
            seed_bytes = seed_path.read_bytes()
            for i in range(25):
                status = layers[i] if i < len(layers) else "N"
                filename = (
                    f"{date_str}_{bundle_no}_{mtrl_no}"
                    f"_{line_no}_L{str(i+1).zfill(2)}_{status}.jpg"
                )
                tmp_path = tmp_dir / filename
                tmp_path.write_bytes(seed_bytes)
                generated_files.append((filename, str(tmp_path)))

            logger.info(f"[FTP] Generated {len(generated_files)} files in {tmp_dir}")

        except Exception as e:
            logger.error(f"[FTP] File generation error: {e}")
            shutil.rmtree(str(tmp_dir), ignore_errors=True)
            return [{"filename": "generation", "status": f"error: {e}"}]

        # FTP 업로드 (blocking I/O → run_in_executor)
        loop = asyncio.get_event_loop()
        upload_results = await loop.run_in_executor(
            None, self._ftp_upload_files, generated_files
        )

        # 업로드 완료 후 img_dir에 복사 (로컬 보관용) + 임시 디렉토리 정리
        try:
            for filename, tmp_path in generated_files:
                dest = img_dir / filename
                try:
                    shutil.move(tmp_path, str(dest))
                except Exception:
                    pass
        finally:
            shutil.rmtree(str(tmp_dir), ignore_errors=True)

        ok_count = sum(1 for r in upload_results if r["status"] == "ok")
        logger.info(f"[FTP] Upload complete: {ok_count}/{len(generated_files)} files OK")
        return upload_results

    def _ftp_upload_files(self, files: list, max_retries: int = 3) -> list:
        """FTP 서버에 파일 목록 업로드 (동기 — executor에서 실행)

        files: [(filename, local_path), ...]
        실패 시 최대 max_retries회 재시도 (재접속 포함)
        업로드 후 ftp.size()로 실제 존재 확인
        """
        import time

        results = []
        ftp = None

        def _connect_ftp():
            """FTP 접속 + 로그인 + cwd"""
            conn = ftplib.FTP(self.ftp_host, timeout=15)
            conn.login(self.ftp_user, self.ftp_pass)
            if self.ftp_dir:
                try:
                    conn.cwd(self.ftp_dir)
                except ftplib.error_perm:
                    logger.warning(f"[FTP] Directory '{self.ftp_dir}' not found, creating...")
                    try:
                        conn.mkd(self.ftp_dir)
                        conn.cwd(self.ftp_dir)
                    except ftplib.all_errors as mkd_err:
                        logger.error(f"[FTP] Failed to create dir '{self.ftp_dir}': {mkd_err}")
            logger.info(f"[FTP] Connected to {self.ftp_host}, cwd={conn.pwd()}")
            return conn

        def _upload_and_verify(conn, filename, local_path, local_size):
            """STOR 후 SIZE로 서버에 실제 존재하는지 확인"""
            with open(local_path, "rb") as f:
                resp = conn.storbinary(f"STOR {filename}", f)
            # STOR 응답 확인 (226 = 전송 완료)
            if not resp.startswith("226"):
                raise ftplib.error_reply(f"Unexpected STOR response: {resp}")
            # SIZE 명령으로 실제 파일 존재+크기 확인
            try:
                remote_size = conn.size(filename)
                if remote_size is None or remote_size != local_size:
                    raise ftplib.error_reply(
                        f"Size mismatch: local={local_size}, remote={remote_size}")
            except ftplib.error_perm:
                # SIZE 미지원 서버 → NLST로 존재 확인
                file_list = conn.nlst()
                if filename not in file_list:
                    raise ftplib.error_reply(f"File not found after STOR: {filename}")

        try:
            ftp = _connect_ftp()

            for filename, local_path in files:
                local_size = os.path.getsize(local_path)
                uploaded = False
                last_err = None

                for attempt in range(1, max_retries + 1):
                    try:
                        _upload_and_verify(ftp, filename, local_path, local_size)
                        uploaded = True
                        break
                    except (ftplib.all_errors, OSError) as e:
                        last_err = e
                        logger.warning(f"[FTP] Attempt {attempt}/{max_retries} "
                                       f"failed {filename}: {e}")
                        # FTP 연결 상태 확인 → 끊어졌으면 재접속
                        try:
                            ftp.pwd()
                        except Exception:
                            logger.info("[FTP] Reconnecting...")
                            try:
                                ftp.quit()
                            except Exception:
                                pass
                            try:
                                ftp = _connect_ftp()
                            except Exception as conn_err:
                                logger.error(f"[FTP] Reconnect failed: {conn_err}")
                        if attempt < max_retries:
                            time.sleep(0.5)

                if uploaded:
                    results.append({"filename": filename, "status": "ok"})
                else:
                    results.append({"filename": filename, "status": f"error: {last_err}"})
                    logger.error(f"[FTP] FAILED after {max_retries} retries: {filename}")

            # 최종 검증: 서버 디렉토리 파일 목록 확인
            try:
                remote_files = ftp.nlst()
                uploaded_names = [f for f, _ in files]
                found = [f for f in uploaded_names if f in remote_files]
                missing = [f for f in uploaded_names if f not in remote_files]
                logger.info(f"[FTP] Verify: {len(found)}/{len(files)} files exist on server")
                if missing:
                    logger.error(f"[FTP] MISSING on server: {missing[:5]}...")
            except Exception as ve:
                logger.warning(f"[FTP] Verify listing failed: {ve}")

        except ftplib.all_errors as e:
            logger.error(f"[FTP] Connection error: {e}")
            for filename, _ in files:
                if not any(r["filename"] == filename for r in results):
                    results.append({"filename": filename, "status": f"ftp_error: {e}"})
        finally:
            if ftp:
                try:
                    ftp.quit()
                except Exception:
                    pass

        return results

    async def send_result_change(self, bundle_no, mtrl_no, line_no, filenames, date=""):
        """TC 1010 판정결과 변경 전송"""
        pkt = TC1010_ResultChange(
            bundle_no=bundle_no,
            mtrl_no=mtrl_no,
            line_no=line_no,
            filenames=filenames,
            date=date,
        )
        raw = pkt.build()
        success = await self.send_packet(raw, "1010")
        return success

    async def start_auto_winding(self, material=None, layers: list = None,
                                layer_count: int = None):
        """자동 권취 시작 — 1002 소재정보 수신 시 1101을 한 번에 전송"""
        if self._auto_winding_task and not self._auto_winding_task.done():
            self._auto_winding_task.cancel()

        mat = material or self.data_store.current_material
        if not mat:
            logger.warning("No material info for auto winding")
            return False

        if layers is not None:
            self.auto_winding_layers = (layers + ["N"] * 25)[:25]
        if layer_count is not None:
            self.auto_winding_layer_count = layer_count

        self._auto_winding_task = asyncio.create_task(self._auto_winding_send(mat))
        await self.ws_manager.broadcast("auto_winding_changed", {"active": True})
        return True

    async def stop_auto_winding(self):
        """자동 권취 중지"""
        if self._auto_winding_task:
            self._auto_winding_task.cancel()
            self._auto_winding_task = None
        await self.ws_manager.broadcast("auto_winding_changed", {"active": False})
        return True

    @property
    def auto_winding_active(self) -> bool:
        return self._auto_winding_task is not None and not self._auto_winding_task.done()

    async def _auto_winding_send(self, material):
        """자동 권취 — L2 소재정보 기반으로 1101 전송

        bundle_no, mtrl_no, line_no → L2 수신 소재정보(1002)에서 가져옴
        layer_count → 25 (전체 레이어)
        layers (판정 상태) → UI에서 설정한 auto_winding_layers 사용
        """
        layers = self.auto_winding_layers
        layer_count = 25  # 항상 전체 25개 레이어
        logger.info(f"[WINDING] Auto send: bundle={material.bundle_no} "
                     f"mtrl={material.mtrl_no} line={material.line_no} "
                     f"layers={''.join(layers[:layer_count])}")

        try:
            await self.send_winding_status(
                bundle_no=material.bundle_no,
                mtrl_no=material.mtrl_no,
                line_no=material.line_no,
                layer_count=layer_count,
                layers=layers,
            )
            logger.info("[WINDING] Complete")
        except asyncio.CancelledError:
            logger.info("[WINDING] Cancelled")
        finally:
            await self.ws_manager.broadcast("auto_winding_changed", {"active": False})

    async def _on_disconnected(self):
        """L2 연결 종료 처리"""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.data_store.connection_state = ConnectionState.DISCONNECTED
        self.data_store.l2_connected_since = None
        self.writer = None
        self.reader = None

        for task in [self._alive_task, self._alive_watchdog_task]:
            if task:
                task.cancel()
        self._alive_task = None
        self._alive_watchdog_task = None

        await self.ws_manager.broadcast("connection_changed", {
            "state": ConnectionState.DISCONNECTED.value,
            "timestamp": now_str,
        })
        logger.info("L2 연결 끊김")

    @staticmethod
    def _obj_to_dict(obj) -> dict:
        result = {}
        for k, v in obj.__dict__.items():
            if isinstance(v, list):
                result[k] = v
            else:
                result[k] = str(v) if v is not None else ""
        return result

    @property
    def is_connected(self) -> bool:
        return self.writer is not None
