# 🔥 파이어가드(FireGuard) 백엔드 API 명세서

- **버전**: v0.1 (초안)
- **작성일**: 2026-08-08
- **백엔드 스택**: Flask / PostgreSQL (`fireguard` 스키마)
- **Base URL**: `http://localhost:5000/api`

---

## 1. 공통 규칙

### 1.1 데이터 표기 표준
- **JSON Key**: `snake_case` (DB 컬럼명과 1:1 매핑)
- **날짜/시간**: ISO 8601 포맷 (`"2026-08-08T14:30:00"`)
- **감지 신뢰도(Confidence)**: `0.0` ~ `1.0` 사이의 소수 (`0.9123`)
- **위도/경도 Coordinates**: 소수점 좌표 (`lat: 37.5665`, `lng: 126.9780`)

### 1.2 인증 방식
- 로그인 성공 시 발급되는 JWT를 요청 헤더에 포함합니다.
```http
Authorization: Bearer <access_token>
```

### 1.3 공통 에러 응답 형식
모든 실패/에러 응답은 동일한 구조로 제공됩니다.

```json
{
  "code": "INVALID_CREDENTIALS",
  "message": "아이디 또는 비밀번호가 일치하지 않습니다."
}
```

| HTTP 상태 코드 | 의미 | 설명 |
|---|---|---|
| `400 Bad Request` | 요청 오류 | 필수 파라미터 누락, 값 데이터 타입 오류 |
| `401 Unauthorized` | 미인증 | 토큰 누락 또는 만료됨 |
| `403 Forbidden` | 권한 없음 | 권한 부족 (예: VIEWER 계정이 ADMIN 전용 API 호출) |
| `404 Not Found` | 리소스 없음 | 요청한 ID의 리소스가 존재하지 않음 |
| `409 Conflict` | 비즈니스 충돌 | 중복 아이디, 유예시간 초과 등 |
| `500 Internal Server Error` | 서버 내부 오류 | 백엔드 서버 처리 실패 |

### 1.4 공통 페이징 응답 형식
목록 조회 API는 `?page=1&size=20` 쿼리 파라미터를 받아 아래 구조로 응답합니다. (page는 1부터 시작)

```json
{
  "items": [ ... ],
  "page": 1,
  "size": 20,
  "total_count": 42,
  "total_pages": 3
}
```

---

## 2. 상태값 (Enum) 정의

| 구분 | Enum 값 | 설명 |
|---|---|---|
| **`user_role`** | `ADMIN` / `VIEWER` | 시스템 관리자 / 조회 전용 계정 |
| **`user_status`** | `ACTIVE` / `SUSPENDED` / `WITHDRAWN` | 정상 / 정지 / 탈퇴 상태 |
| **`cctv_status`** | `ACTIVE` / `INACTIVE` / `ERROR` | 정상 수신 / 동작 중지 / 연결 오류 |
| **`event_status`** | `CONFIRMED` / `DISMISSED` | 감지 확정 / 기준 미달(오탐 처리) |
| **`event_class`** | `FLAME` / `SMOKE` / `FLAME_SMOKE` | 불꽃 감지 / 연기 감지 / 둘 다 감지 |
| **`media_type`** | `FRAME` / `CLIP` | 정지 프레임 이미지 / 짧은 영상 클립 |
| **`alert_level`** | `1` / `2` / `3` | 1차 발생 / 승격 / 최종 경보 |
| **`alert_channel`** | `PUSH` / `SMS` | 앱 푸시 알림 / 문자 메세지 |
| **`alert_status`** | `SENT` / `READ` / `CANCELED` / `NO_RESPONSE` | 발송됨 / 확인 완료 / 사용자 취소됨 / 무응답 |
| **`report_status`** | `SENDING` / `DISPATCHED` / `NO_RESPONSE` / `FAILED` | 119 전송중 / 출동 접수됨 / 무응답 승계 / 전송 실패 |

---

## 3. API 엔드포인트 요약 목록

| 카테고리 | Method | Endpoint | 인증 | 설명 |
|---|---|---|---|---|
| **Auth** | `POST` | `/api/auth/login` | O (미필요) | 관리자 로그인 및 JWT 발급 |
| **Auth** | `GET` | `/api/auth/me` | 🔒 로그인 | 로그인 사용자 세션 정보 조회 |
| **Users** | `GET` | `/api/users` | 🔒 ADMIN | 사용자 목록 조회 (페이징) |
| **Users** | `POST` | `/api/users` | 🔒 ADMIN | 새로운 사용자 등록 |
| **Users** | `PUT` | `/api/users/<user_no>` | 🔒 ADMIN/본인 | 사용자 정보 수정 및 상태 변경 |
| **CCTV** | `GET` | `/api/cctvs` | 🔒 로그인 | 연동 CCTV 목록 조회 |
| **CCTV** | `GET` | `/api/cctvs/<cctv_no>` | 🔒 로그인 | 특정 CCTV 단건 상세 조회 |
| **CCTV** | `POST` | `/api/cctvs` | 🔒 ADMIN | 신규 CCTV 등록 |
| **CCTV** | `PUT` | `/api/cctvs/<cctv_no>` | 🔒 ADMIN | CCTV 정보 수정 / 상태 변경 |
| **Events** | `GET` | `/api/events` | 🔒 로그인 | 화재 감지 이벤트 이력 목록 조회 |
| **Events** | `GET` | `/api/events/<event_no>` | 🔒 로그인 | 특정 이벤트 상세 (미디어, 알림, 신고이력 포함) |
| **Alerts** | `GET` | `/api/alerts` | 🔒 로그인 | 내 관리자 알림 목록 조회 |
| **Alerts** | `POST` | `/api/alerts/<alert_no>/respond` | 🔒 로그인 | 알림 확인(`READ`) 또는 오탐 취소(`CANCEL`) 처리 |
| **Agencies** | `GET` | `/api/agencies` | 🔒 로그인 | 소방서 목록 조회 |
| **Agencies** | `POST` | `/api/agencies` | 🔒 ADMIN | 소방서 정보 등록 |
| **Agencies** | `PUT` | `/api/agencies/<agency_no>` | 🔒 ADMIN | 소방서 정보 수정 / 비활성화 |
| **Reports** | `GET` | `/api/reports` | 🔒 로그인 | 119 신고 발송 이력 전체 조회 |

---

## 4. 상세 API 스펙

### 4.1 인증 (Auth)

#### 1) `POST /api/auth/login` (로그인)
- **설명**: 관리자 계정 로그인 및 JWT 발급
- **Request Body**:
  ```json
  {
    "user_id": "admin01",
    "user_pw": "password123!"
  }
  ```
- **Response 200**:
  ```json
  {
    "access_token": "eyJhbGciOiJIUzI1NiIs...",
    "user": {
      "user_no": 1,
      "user_id": "admin01",
      "user_name": "홍길동",
      "user_role": "ADMIN"
    }
  }
  ```
- **Error Responses**:
  - `401 INVALID_CREDENTIALS`: 아이디 또는 비밀번호 불일치
  - `403 ACCOUNT_SUSPENDED`: 계정 이용 정지 상태
  - `403 ACCOUNT_WITHDRAWN`: 탈퇴 처리된 계정

#### 2) `GET /api/auth/me` (세션 확인)
- **설명**: 현재 로그인한 사용자의 프로필 조회
- **Response 200**:
  ```json
  {
    "user_no": 1,
    "user_id": "admin01",
    "user_name": "홍길동",
    "user_email": "hong@fireguard.kr",
    "user_phone": "010-1234-5678",
    "user_role": "ADMIN",
    "user_status": "ACTIVE"
  }
  ```

---

### 4.2 사용자 관리 (Users)

#### 1) `GET /api/users` (사용자 목록)
- **Query Params**: `user_status` (선택), `page` (기본 1), `size` (기본 20)
- **Response 200**:
  ```json
  {
    "items": [
      {
        "user_no": 1,
        "user_id": "admin01",
        "user_name": "홍길동",
        "user_email": "hong@fireguard.kr",
        "user_phone": "010-1234-5678",
        "user_role": "ADMIN",
        "user_status": "ACTIVE",
        "user_created_at": "2026-08-01T09:00:00"
      }
    ],
    "page": 1,
    "size": 20,
    "total_count": 1,
    "total_pages": 1
  }
  ```

#### 2) `POST /api/users` (사용자 등록/회원가입)
- **Request Body**:
  ```json
  {
    "user_id": "user02",
    "user_pw": "Password123!",
    "user_name": "김철수",
    "user_email": "chulsoo@naver.com",
    "user_phone": "010-9876-5432",
    "user_role": "VIEWER",
    "user_gender": "남자",
    "user_address": "서울시 종로구 세종대로 1"
  }
  ```
- **Response 201**: `{ "user_no": 2 }`
- **Error**: `409 DUPLICATE_USER_ID` (아이디 중복)

#### 3) `PUT /api/users/<user_no>` (사용자 정보 수정)
- **Request Body** (수정할 필드만 전송):
  ```json
  {
    "user_name": "김철수",
    "user_email": "new@fireguard.kr",
    "user_phone": "010-9999-8888",
    "user_status": "SUSPENDED"
  }
  ```
- **Response 200**: `{ "user_no": 2 }`

---

### 4.3 CCTV 카메라 관리 (CCTV)

#### 1) `GET /api/cctvs` (카메라 목록)
- **Query Params**: `cctv_status` (선택)
- **Response 200**:
  ```json
  {
    "items": [
      {
        "cctv_no": 1,
        "user_no": 1,
        "cctv_name": "정문 카메라",
        "cctv_location": "본관 정문 앞",
        "cctv_lat": 37.5665,
        "cctv_lng": 126.9780,
        "cctv_stream_url": "rtsp://192.168.0.10:554/stream1",
        "cctv_width": 1920,
        "cctv_height": 1080,
        "cctv_status": "ACTIVE",
        "cctv_created_at": "2026-08-01T09:00:00"
      }
    ]
  }
  ```

#### 2) `POST /api/cctvs` (카메라 등록)
- **Request Body**:
  ```json
  {
    "cctv_name": "후문 카메라",
    "cctv_location": "본관 후문 주차장",
    "cctv_lat": 37.5670,
    "cctv_lng": 126.9785,
    "cctv_stream_url": "rtsp://192.168.0.11:554/stream1",
    "cctv_width": 1920,
    "cctv_height": 1080
  }
  ```
- **Response 201**: `{ "cctv_no": 2 }`

---

### 4.4 화재 이벤트 (Fire Events)

#### 1) `GET /api/events` (이벤트 이력 조회)
- **Query Params**: `event_status`, `event_class`, `cctv_no`, `date_from`, `date_to`, `include_test`, `page`, `size`
- **Response 200**:
  ```json
  {
    "items": [
      {
        "event_no": 12,
        "cctv_no": 1,
        "cctv_name": "정문 카메라",
        "cctv_location": "본관 정문 앞",
        "event_status": "CONFIRMED",
        "event_class": "FLAME",
        "event_first_detected_at": "2026-08-08T14:29:50",
        "event_detected_at": "2026-08-08T14:30:00",
        "event_confidence": 0.9123,
        "event_is_test": false,
        "thumbnail_url": "/media/events/12/frame_001.jpg"
      }
    ],
    "page": 1,
    "size": 20,
    "total_count": 42,
    "total_pages": 3
  }
  ```

#### 2) `GET /api/events/<event_no>` (이벤트 상세조회)
- **Response 200**:
  ```json
  {
    "event_no": 12,
    "event_status": "CONFIRMED",
    "event_class": "FLAME",
    "event_first_detected_at": "2026-08-08T14:29:50",
    "event_detected_at": "2026-08-08T14:30:00",
    "event_detected_frames": 32,
    "event_threshold_frames": 30,
    "event_confidence": 0.9123,
    "event_is_test": false,
    "cctv": {
      "cctv_no": 1,
      "cctv_name": "정문 카메라",
      "cctv_location": "본관 정문 앞",
      "cctv_lat": 37.5665,
      "cctv_lng": 126.9780
    },
    "media": [
      {
        "media_no": 30,
        "media_type": "FRAME",
        "media_url": "/media/events/12/frame_001.jpg",
        "media_confidence": 0.9123,
        "media_captured_at": "2026-08-08T14:30:00",
        "media_is_primary": true,
        "media_detections": [
          { "cls": "flame", "conf": 0.910, "box": [0.238, 0.259, 0.047, 0.113] },
          { "cls": "person", "conf": 0.774, "box": [0.412, 0.688, 0.031, 0.142] }
        ]
      }
    ],
    "alerts": [ ... ],
    "reports": [ ... ]
  }
  ```
> 💡 `media_detections`의 `box`는 `[x_center, y_center, width, height]` 소수점 비율 좌표(YOLO xywhn)입니다.

---

### 4.5 관리자 알림 (Alerts)

#### 1) `GET /api/alerts` (내 알림 목록)
- **Response 200**:
  ```json
  {
    "items": [
      {
        "alert_no": 5,
        "event_no": 12,
        "event_class": "FLAME",
        "cctv_name": "정문 카메라",
        "alert_level": 1,
        "alert_channel": "PUSH",
        "alert_status": "SENT",
        "alert_sent_at": "2026-08-08T14:30:05",
        "alert_deadline_at": "2026-08-08T14:33:05",
        "alert_responded_at": null
      }
    ]
  }
  ```

#### 2) `POST /api/alerts/<alert_no>/respond` (알림 응답 처리)
- **Request Body**:
  ```json
  {
    "action": "CANCEL" // READ (화재 확인) 또는 CANCEL (오탐 취소)
  }
  ```
- **Response 200**:
  ```json
  {
    "alert_no": 5,
    "alert_status": "CANCELED",
    "alert_responded_at": "2026-08-08T14:31:00"
  }
  ```
- **Errors**:
  - `409 DEADLINE_PASSED`: 유예 마감시간 초과 후 취소 요청 시도
  - `409 ALREADY_RESPONDED`: 이미 처리된 알림

---

### 4.6 소방서 (Agencies) & 119 신고 (Reports)

#### 1) `GET /api/reports` (119 신고 내역 조회)
- **Response 200**:
  ```json
  {
    "items": [
      {
        "report_no": 3,
        "event_no": 12,
        "agency_no": 2,
        "agency_name": "종로소방서",
        "report_sequence": 1,
        "report_external_id": "R-20260808-0012",
        "report_trigger_reason": "NO_RESPONSE_TIMEOUT",
        "report_status": "DISPATCHED",
        "report_address": "서울시 종로구 세종대로 1",
        "report_distance_km": 1.234,
        "report_attempt_count": 1,
        "reported_at": "2026-08-08T14:33:10",
        "report_dispatched_at": "2026-08-08T14:33:40"
      }
    ]
  }
  ```

---

## 5. 비고 및 검토 사항 (Roadmap)

- **실시간 통신 방식**: 웹소켓(WebSocket) 또는 SSE(Server-Sent Events) 도입 검토
- **미디어 파일 수신**: 정적 파일 서버 방식 vs 백엔드 스트리밍 API 서빙
- **대시보드 통계 API**: 일별/월별 화재 감지 수 통계 API v0.2 반영 예정
