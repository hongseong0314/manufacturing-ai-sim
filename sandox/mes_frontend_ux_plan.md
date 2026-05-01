# 반도체 AI MES 프론트엔드 UX 초안

## 목표

API를 만들기 전에 먼저 사용자가 무엇을 보게 될지 고정한다. 이 프론트는
일반 MES 메뉴 화면이 아니라, 현재 프로젝트의 강점인 simulator-backed
decision chain을 보여주는 개발용 관제 화면에서 시작한다.

핵심 UX 문장:

```text
AI는 추천하고, Rule Engine은 검증하고, MES만 실행한다.
```

따라서 첫 화면은 AI 점수판이 아니라 다음을 동시에 보여줘야 한다.

- 현재 WIP와 병목 공정
- 장비 상태와 dispatch 후보
- `L4 -> L3 -> L1 -> L2` 추천 chain
- Rule Engine 검증 결과
- simulator action / command
- event timeline과 `correlation_id`

## 사용자

| 사용자 | 관심사 | 화면에서 바로 보여야 하는 것 |
|---|---|---|
| Dispatcher | 지금 어떤 Lot을 어느 장비에 넣을지 | Dispatch candidates, rule status, command |
| Process Engineer | Recipe와 품질 위험 | L2 recipe/APC, QA drift, recipe status |
| Equipment Engineer | 장비 상태와 영향도 | RUN/IDLE/DOWN, batch, health state |
| MES Developer | 연결성과 재현성 | recommendation ids, parent chain, events |
| AI Engineer | 추천 품질과 feature | feature snapshot, score, confidence, reasons |

## 첫 MVP 화면

### 1. Fab Control Room

전체 공장 또는 simulator line의 현재 상태를 본다.

- KPI strip: total WIP, completed, equipment utilization, queue risk
- Stage board: A/B/C stage별 WIP, idle equipment, rework/incoming
- Active decision chain: L4, L3, L1, L2
- Rule Engine gate: PASSED/REJECTED, reasons
- Validated command: simulator action preview

### 2. Stage Dispatch Board

현재 병목 stage를 기준으로 후보를 비교한다.

- stage selector: A, B, C
- candidate table: equipment, task/wafer ids, task type, rule precheck
- AI selected row
- Rule validation panel
- command preview

### 3. Decision Chain Inspector

AI MES의 차별화 화면이다. 실행 command가 어디서 왔는지 역추적한다.

- `correlation_id`
- L4 objective recommendation
- L3 stage priority recommendation
- L1 dispatch/pack recommendation
- L2 recipe/APC recommendation
- parent recommendation chain
- feature snapshot ids
- validation result

### 4. Lot/Wafer Trace

생산 객체 관점 화면이다.

- lot list
- wafer map
- current operation
- equipment assignment
- QA result
- event history
- genealogy link

### 5. Equipment and Recipe Monitor

장비와 recipe가 실제 실행 가능 상태인지 본다.

- equipment status matrix
- current batch
- equipment health state
- recipe id/version
- recipe compare/download status
- maintenance or replacement flag

### 6. Evaluator Console

개발 단계에서 특히 중요하다. 하네스가 만든 결과가 진짜 연결됐는지 본다.

- required layers present
- single correlation id
- parent chain integrity
- feature snapshot presence
- rule validation passed
- simulator action matched
- env step executed

## 정보 구조

```text
Fab Control Room
  -> Stage Dispatch Board
  -> Decision Chain Inspector
  -> Lot/Wafer Trace
  -> Equipment and Recipe Monitor
  -> Event/Genealogy Audit
  -> Evaluator Console
```

## API로 연결될 위치

| UI 영역 | 향후 API |
|---|---|
| KPI strip | `GET /api/v1/kpis/fab`, `GET /api/v1/kpis/ai` |
| Stage board | `GET /api/v1/wip`, `GET /api/v1/equipment` |
| Candidate table | `GET /api/v1/dispatch/candidates` |
| Decision chain | `GET /api/v1/ai/recommendations?correlation_id=...` |
| Rule gate | `POST /api/v1/rules/validate` |
| Command preview | `POST /api/v1/commands/track-in` |
| Event timeline | `GET /api/v1/events?correlation_id=...` |
| Lot trace | `GET /api/v1/lots/{lot_id}` |
| Genealogy | `GET /api/v1/genealogy/lot/{lot_id}` |

## 디자인 방향

`awesome-design-md`를 확인한 결과, 이 프로젝트에는 IBM/Carbon 계열의
enterprise control UI가 가장 적합하다. 다만 특정 브랜드를 그대로 복제하지
않고, 프로젝트 루트의 `DESIGN.md`에 반도체 MES 전용 규칙으로 재정의한다.

방향:

- 밝은 neutral surface
- compact table-first layout
- status color 중심
- AI는 purple accent
- command/action은 blue accent
- 6px 이하 radius
- no marketing hero
- no decorative gradient blobs

## Scrappy Prototype 범위

이번 프로토타입은 API 없이 mock data로 만든다.

포함:

- Fab Control Room
- Stage Dispatch Board
- Decision Chain Inspector
- Rule Engine Gate
- Equipment Matrix
- Event Timeline
- Evaluator Checklist

제외:

- 실제 FastAPI 연동
- 사용자 인증
- PostgreSQL 저장
- websocket live update
- 실제 AI serving

## 다음 개발 순서

1. 정적 프로토타입으로 화면 구조 합의
2. `src/mes/store.py`로 recommendation/event/command audit 저장
3. FastAPI read API부터 연결
4. `harness.run()` 결과를 API response로 노출
5. 프론트 mock data를 API data로 교체
6. command 실행은 Rule Engine 통과 후에만 활성화

