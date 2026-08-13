from flask import Blueprint, jsonify, request, g
from errors import ApiError
from auth import login_required, admin_required
from db import query_one, execute

# 블루프린트 생성 (URL prefix 설정)
request_role_bp = Blueprint("request_role", __name__, url_prefix="/api/admin")


@request_role_bp.post("/request-upgrade")
@login_required
def request_admin_upgrade():
    """일반 회원이 관리자 권한 승인 요청을 보낸다 (계정 상태: USER -> PENDING)."""
    print(f"[DEBUG] g.user: {g.user}")
    user_no = g.user.get("user_no")
    
    # DB에서 유저 조회 (권한과 상태 모두 조회)
    user = query_one(
        "SELECT user_no, user_role, user_status FROM fireguard.users WHERE user_no = %s", 
        (user_no,)
    )
    if not user:
        raise ApiError(404, "USER_NOT_FOUND", "사용자를 찾을 수 없습니다.")
    
    current_role = user.get("user_role")
    current_status = user.get("user_status")
    
    # 이미 관리자이거나 대기 중인 경우 예외 처리
    if current_role == "ADMIN":
        raise ApiError(400, "ALREADY_ADMIN", "이미 관리자 계정입니다.")
    if current_status == "PENDING":
        raise ApiError(400, "ALREADY_PENDING", "이미 승인 대기 중인 계정입니다.")
    
    # 계정 상태를 PENDING(승인 대기)으로 변경 (권한은 그대로 유지)
    execute(
        "UPDATE fireguard.users SET user_status = %s WHERE user_no = %s", 
        ("PENDING", user_no)
    )
    
    return jsonify({"message": "관리자 권한 승인 요청이 완료되었습니다."})


@request_role_bp.patch("/handle-request/<int:target_user_no>")
@admin_required
def handle_admin_request(target_user_no: int):
    """관리자가 승인 대기 중인 유저의 요청을 승인(ADMIN) 또는 거절(USER)한다."""
    
    # silent=True를 추가하여 Content-Type이 잘못되었거나 본문이 비어있어도 파싱 에러 없이 안전하게 처리
    data = request.get_json(silent=True) or {}
    action = data.get("action")  # "approve" 또는 "reject"
    
    # [디버그 로그] 서버 터미널에서 실제 수신 데이터 확인
    print(f"\n[DEBUG] target_user_no: {target_user_no}")
    print(f"[DEBUG] Request Body JSON: {data}")
    print(f"[DEBUG] Extracted action: {action}")
    
    # 대상 유저 조회
    target_user = query_one(
        "SELECT user_no, user_id, user_role, user_status FROM fireguard.users WHERE user_no = %s", 
        (target_user_no,)
    )
    
    print(f"[DEBUG] DB target_user: {target_user}")
    
    if not target_user:
        raise ApiError(404, "USER_NOT_FOUND", "대상을 찾을 수 없습니다.")
    
    # 대상 유저가 PENDING 상태인지 확인
    current_status = target_user.get("user_status")
    if current_status != "PENDING":
        print(f"[DEBUG] 400 차단: 유저 상태가 PENDING이 아님 (현재 상태: {current_status})")
        raise ApiError(400, "NOT_PENDING", "승인 대기 중인 유저가 아닙니다.")
    
    # 액션에 따른 처리 (승인 vs 거절)
    if action == "approve":
        new_role = "ADMIN"
        new_status = "ACTIVE"
        message = f"{target_user.get('user_id')} 님의 관리자 승인이 완료되었습니다."
    elif action == "reject":
        new_role = "USER"
        new_status = "ACTIVE"
        message = f"{target_user.get('user_id')} 님의 관리자 승인 요청이 거절되었습니다."
    else:
        print(f"[DEBUG] 400 차단: 올바르지 않은 action 값 ({action})")
        raise ApiError(400, "INVALID_ACTION", "올바르지 않은 액션입니다. ('approve' 또는 'reject' 입력 필요)")
    
    # DB 업데이트 실행 (권한과 상태값 모두 업데이트)
    execute(
        "UPDATE fireguard.users SET user_role = %s, user_status = %s WHERE user_no = %s", 
        (new_role, new_status, target_user_no)
    )
    
    return jsonify({"message": message})