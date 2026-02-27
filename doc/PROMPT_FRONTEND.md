# Claude Code Prompt: Frontend Agent

> **이 프롬프트를 Claude Code에 입력하여 Frontend Agent를 구현하시오.**  
> **반드시 `PRD_LV2_SYSTEM.md`를 먼저 읽은 후 작업을 시작할 것.**

---

## 역할

너는 동국제강 CS공장 권취상태 모니터링 시스템의 **Frontend Agent** 개발자다.  
산업용 모니터링 대시보드를 React로 구현해야 한다.

## 작업 디렉토리

`D:\DATA\python\LLM_LV2_TEST\frontend\`

## 사전 조건

1. 프로젝트 루트의 `PRD_LV2_SYSTEM.md`를 읽어라. 프로토콜과 데이터 구조가 거기에 있다.
2. Backend API는 `http://localhost:8080` (REST), `ws://localhost:8080/ws` (WebSocket)에서 제공된다.

## 디자인 철학

**이것은 제철소 컨트롤룸 모니터링 화면이다. 스타트업 대시보드가 아니다.**

```
[절대 금지] 둥근 모서리 > 8px
[절대 금지] box-shadow (대신 border 사용)
[절대 금지] 그래디언트 카드 배경
[절대 금지] 이모지, 귀여운 일러스트, 마스코트
[절대 금지] 보라/핑크/코랄 색상
[절대 금지] Inter, Roboto, Poppins 폰트
[절대 금지] 과도한 여백 (화면 부동산 낭비)
[절대 금지] 요소를 움직이는 hover 애니메이션
[절대 금지] "Loading..." 에 personality 넣기
```

### 색상 시스템

```css
/* 다크 테마 (기본) */
--bg-primary: #0d1117;
--bg-secondary: #161b22;
--bg-tertiary: #1c2333;
--border-default: #30363d;
--text-primary: #e6edf3;
--text-secondary: #8b949e;

/* 상태 색상 */
--status-ok: #3fb950;         /* 초록 — N (Normal) */
--status-warning: #d29922;    /* 노랑 — T (Twist) */
--status-critical: #f85149;   /* 빨강 — H (Hooking) */
--status-offline: #6e7681;    /* 회색 — U (Unmeasured) / Disconnected */
--status-info: #58a6ff;       /* 파랑 — 정보성 */
```

### 폰트

```html
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Sans+Condensed:wght@500;600;700&family=JetBrains+Mono:wght@400;500&family=Noto+Sans+KR:wght@400;500;700&display=swap" rel="stylesheet">
```

- UI 라벨/내비: `IBM Plex Sans`, `Noto Sans KR`
- 데이터 값/코드: `JetBrains Mono`
- 섹션 제목: `IBM Plex Sans Condensed`

## 구현 요구사항

### 1. 프로젝트 구조

React (Vite 또는 CRA) 사용. Tailwind CSS는 CDN으로 로드.

```
frontend/
├── index.html
├── package.json
├── vite.config.js
└── src/
    ├── App.jsx                # 메인 레이아웃
    ├── main.jsx               # 엔트리포인트
    ├── styles/
    │   └── industrial.css     # 커스텀 CSS 변수 + 산업용 스타일
    ├── hooks/
    │   ├── useWebSocket.js    # WebSocket 연결 + 자동 재접속
    │   └── useApi.js          # REST API 호출
    ├── components/
    │   ├── layout/
    │   │   ├── Header.jsx     # 상단 상태바
    │   │   └── Sidebar.jsx    # 좌측 내비게이션
    │   ├── dashboard/
    │   │   ├── ConnectionStatus.jsx   # TCP 연결 + Alive 상태
    │   │   ├── CoilInfo.jsx           # 현재 코일 정보 카드
    │   │   ├── LayerGrid.jsx          # ★ 25-Layer 권취상태 시각화
    │   │   ├── LineStatus.jsx         # A/B 라인 가동상태
    │   │   └── ProductionInfo.jsx     # 생산/소재 정보
    │   ├── control/
    │   │   ├── SetupPanel.jsx         # 1001 생산정보 전송 폼
    │   │   ├── MaterialPanel.jsx      # 1002 소재정보 전송 폼
    │   │   └── ResultChangePanel.jsx  # 1010 판정결과 변경 폼
    │   └── common/
    │       ├── LogPanel.jsx           # 전문 송수신 로그
    │       ├── StatusDot.jsx          # 상태 표시 LED
    │       └── MonoValue.jsx          # 모노스페이스 데이터값
    └── utils/
        └── constants.js       # 상태코드, 색상 매핑
```

### 2. 메인 레이아웃 (`App.jsx`)

```
┌─────────────────────────────────────────────────────────┐
│ [Header] TCP: ●Connected | Alive: ●OK (cnt:0042)       │
│ | Last RX: 14:30:25 | Work A: 정상 | Work B: 정상      │
├──────┬──────────────────────────────────────────────────┤
│ Side │                                                  │
│ bar  │  ┌─────────────┐ ┌───────────────────────────┐  │
│      │  │ 코일 정보   │ │   25-Layer 권취상태       │  │
│ 대시 │  │ Bundle:     │ │   [시각화 그리드]         │  │
│ 보드 │  │ MTRL:       │ │                           │  │
│      │  │ Line: A     │ │   L01[N] L02[T] L03[N]   │  │
│ 코일 │  │ 강종:       │ │   L04[N] L05[H] ...      │  │
│ 목록 │  │ 제품명:     │ │   ...         L25[U]     │  │
│      │  └─────────────┘ └───────────────────────────┘  │
│ 조작 │  ┌─────────────────────────────────────────────┐│
│      │  │ 생산정보 | 소재정보 | 판정변경  [탭 조작]  ││
│ 로그 │  │ (입력 폼)                                   ││
│      │  └─────────────────────────────────────────────┘│
│ 설정 │  ┌─────────────────────────────────────────────┐│
│      │  │ 전문 로그 (시간순, TC 필터)                 ││
│      │  └─────────────────────────────────────────────┘│
└──────┴──────────────────────────────────────────────────┘
```

대시보드 전체 레이아웃:
```css
.dashboard {
  display: grid;
  grid-template-columns: 220px 1fr;
  grid-template-rows: 48px 1fr;
  height: 100vh;
  overflow: hidden;
  background: var(--bg-primary);
}
```

### 3. ★ 핵심 컴포넌트: LayerGrid (25-Layer 권취상태)

이 컴포넌트가 전체 시스템의 핵심이다. 권취 코일의 25개 레이어 상태를 실시간으로 시각화한다.

**표현 방식** (택 1 또는 조합):

**방식 A — 수직 스택 (코일 단면 느낌)**:
```
  ┌─────────────┐
  │ L25  [U]    │  ← 최상단 레이어 (미측정)
  │ L24  [N]    │
  │ ...         │
  │ L03  [N]    │
  │ L02  [T]    │  ← 꼬임 발생
  │ L01  [N]    │  ← 최하단 레이어
  └─────────────┘
```

**방식 B — 5×5 그리드**:
```
  L01[N] L02[T] L03[N] L04[N] L05[H]
  L06[N] L07[N] L08[N] L09[T] L10[N]
  L11[N] L12[N] L13[N] L14[N] L15[N]
  L16[N] L17[N] L18[N] L19[N] L20[U]
  L21[U] L22[U] L23[U] L24[U] L25[U]
```

**각 레이어 셀**:
```jsx
function LayerCell({ index, status, isNew }) {
  // status: "N" | "T" | "H" | "U"
  // isNew: 방금 업데이트된 레이어 (짧은 플래시 애니메이션)
  
  const colors = {
    N: { bg: '#3fb950', label: 'Normal' },
    T: { bg: '#d29922', label: 'Twist' },
    H: { bg: '#f85149', label: 'Hooking' },
    U: { bg: '#6e7681', label: 'Unmeasured' },
  };
  
  return (
    <div className={`layer-cell status-${status} ${isNew ? 'value-updated' : ''}`}>
      <span className="layer-index">L{String(index).padStart(2, '0')}</span>
      <span className="layer-status">{status}</span>
    </div>
  );
}
```

**값 업데이트 플래시**:
```css
@keyframes value-update {
  0% { background-color: rgba(88, 166, 255, 0.3); }
  100% { background-color: transparent; }
}
.value-updated { animation: value-update 800ms ease-out; }
```

**요약 통계**:
- 레이어 상태별 카운트: N: 18 | T: 3 | H: 1 | U: 3
- 이상 비율: (T+H) / total × 100

### 4. WebSocket 훅 (`useWebSocket.js`)

```javascript
// ws://localhost:8080/ws 연결
// 자동 재접속 (3초 대기 후)
// 
// 수신 이벤트:
//   connection_changed → 연결 상태 업데이트
//   alive_received → Alive 카운터 + 가동상태 업데이트
//   winding_status → LayerGrid 업데이트
//   packet_log → 로그 패널 추가
//
// 상태 관리:
//   wsState: "connecting" | "connected" | "disconnected"
//   reconnectCount: number
```

### 5. 조작 패널 (Control Panel)

탭으로 구분된 3개 폼:

**생산정보 (1001)**:
- 제품명 (6자), 규격약호 (40자), 강종 (7자)
- QTB선속, SPL_A선속, SPL_B선속 (숫자, ×100)
- [전송] 버튼 → `POST /api/setup`

**소재정보 (1002)**:
- 번들번호 (10자), 강편번호 (10자), HEAT번호 (6자)
- 규격약호, 강종, 제품명
- 라인 (A/B 라디오), 선속 3개, QTB온도
- [전송] 버튼 → `POST /api/material`

**판정결과 변경 (1010)**:
- 번들번호, 강편번호, 라인
- 파일명 10개 입력 (각 50자 이내)
- [전송] 버튼 → `POST /api/result-change`

**폼 스타일 규칙**:
```css
/* 입력 필드 — 산업용 느낌 */
input, select {
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  color: var(--text-primary);
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.875rem;
  padding: 6px 10px;
  border-radius: 3px;  /* 최소 라운딩 */
}

/* 버튼 */
button.action {
  background: var(--status-info);
  color: #fff;
  border: none;
  padding: 8px 20px;
  font-weight: 600;
  border-radius: 4px;  /* 최대 4px */
  cursor: pointer;
  transition: opacity 150ms;
}
button.action:hover { opacity: 0.85; }
button.action:disabled { opacity: 0.4; cursor: not-allowed; }
```

### 6. 로그 패널 (`LogPanel.jsx`)

```
┌─────────────────────────────────────────────────────────┐
│ 전문 로그  [All ▾] [TX ▾] [RX ▾]  [1001] [1101] [...]  │
├─────────────────────────────────────────────────────────┤
│ 14:30:25.123 RX TC=1101 72B  S78588B031 Line=A L=18    │
│ 14:30:20.001 TX TC=1099 64B  Alive cnt=0042            │
│ 14:30:15.892 RX TC=1199 52B  cnt=0041 A=01 B=01        │
│ 14:29:50.100 TX TC=1002 256B S78588B031 BL1600 Line=A  │
│ ...                                                     │
└─────────────────────────────────────────────────────────┘
```

- 시간 역순 표시 (최신이 위)
- TC 코드별 필터
- 방향별 필터 (TX/RX)
- 로그 항목에 raw ASCII 보기 토글
- 모노스페이스 폰트 필수

### 7. 반응형은 불필요

이 화면은 컨트롤룸 모니터(21~27인치, 1920×1080 이상)에서만 사용된다.  
모바일/태블릿 대응은 하지 마라. 최소 해상도 1280×720 기준으로 구현.

## 빌드 및 실행

```bash
cd D:\DATA\python\LLM_LV2_TEST\frontend
npm install
npm run dev
# → http://localhost:5173 (Vite 기본)
```

개발 중에는 Backend가 `localhost:8080`에서 실행 중이어야 한다.

## 주의사항

1. **WebSocket 재연결**: 반드시 자동 재접속 구현. 백엔드 재시작해도 프론트가 자동 복구되어야 한다.
2. **데이터 없을 때**: 연결 안 된 상태, 데이터 없는 상태에 대한 빈 상태 UI를 만들어라. placeholder 이미지 대신 의미 있는 빈 상태 메시지.
3. **한국어**: UI 라벨은 한국어 사용. 기술 용어(TC Code, Alive 등)는 영어 병기.
4. **실시간성**: WebSocket으로 받은 데이터는 즉시 반영. polling 금지.
