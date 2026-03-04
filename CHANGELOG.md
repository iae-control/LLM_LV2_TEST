# CHANGELOG — SPL Winding Status Monitor

## [0.3.0] - 2026-03-04

### Added
- **자동 권취 단일패킷 전송**: 1002 소재정보 수신 시 25개 레이어를 단일 TC 1101 패킷으로 전송 (레이어별 순차 전송 제거)
- **FTP seed 이미지 업로드**: 1101 전송 시 seed.jpg를 레이어별로 복사/리네임하여 FTP 서버 RECV 폴더로 업로드
- **자동 권취 활성화 토글**: `auto_winding_enabled` ON/OFF를 UI에서 제어 (기본값 OFF)
- **자동 권취 레이어 설정 API**: `/api/set-auto-winding-config`로 레이어 상태 사전 설정
- **1101/1010 날짜모드 지원**: 수동/자동 날짜 선택 (Date 필드 14자리)
- **FTP CLI 인자**: `--ftp-host`, `--ftp-user`, `--ftp-pass`, `--ftp-dir` 옵션 추가

### Fixed
- **FTP 파일 25개 고정**: `layer_count`와 무관하게 항상 25개 레이어 파일 생성
- **FTP 임시 디렉토리 생성**: 파일 잠금 방지를 위해 temp 디렉토리에 생성 후 업로드
- **FTP 업로드 재시도**: 개별 파일 실패 시 최대 3회 재시도 + FTP 재접속
- **FTP STOR 검증**: 업로드 후 SIZE 명령으로 서버 파일 크기 확인, 불일치 시 재시도
- **FTP cwd 실패 시 자동 생성**: RECV 폴더 미존재 시 `mkd`로 자동 생성
- **시뮬레이터 auto_winding 수정**: `AutoWindingEngine` 레이어별 순차 전송 + random 제거

### Changed
- `auto_winding_enabled` 기본값 `True` → `False` (1002 수신 시 자동 전송 비활성)
- 프론트엔드 권취 컨트롤: 활성화 토글 / 즉시 전송 버튼 분리

---

## [0.2.0] - 2026-03-04

### Added
- 대시보드 전문로그 패널 flex 레이아웃 적용
- `GET /` 라우트: `frontend/index.html` 직접 서빙

---

## [0.1.2] - 2026-02-28

### Added
- 로그 엔트리 확장 기능: 패킷 원문 + 필드별 색상 hex 뷰
- TC 1010 판정변경 수신 데이터 프론트엔드 표시

### Fixed
- 1010 수동전송, Alive 중단, 로그 확장 버그 5건 일괄 수정

---

## [0.1.1] - 2026-02-27

### Added
- 수동 1101 전송 폼: 공정정보 없이도 L2에 권취상태 전송 가능
- 전문로그 페이지 로그목록 전체 높이 사용

### Fixed
- `main.py` sys.path 추가: 다른 경로에서 실행 시 ModuleNotFoundError 수정

### Changed
- L2 Server → SPL Client 아키텍처 전환

---

## [0.1.0] - 2026-02-27

### Added
- 동국제강 CS공장 LV2 권취상태 모니터링 시스템 초기 구현
- ASCII 고정길이 프로토콜 (TC 1001/1002/1010/1099/1101/1199)
- Python asyncio TCP Client + FastAPI REST/WebSocket (port 8080)
- CDN 기반 React 프론트엔드 대시보드
- SPL 시뮬레이터 (`spl_simulator/`)
- pytest 141개 테스트
