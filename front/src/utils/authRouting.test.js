import test from 'node:test';
import assert from 'node:assert/strict';
import {
  createAuthReturnPath,
  hasAllowedRole,
  sanitizeAuthReturnPath,
} from './authRouting.js';

test('보호 경로와 쿼리스트링만 로그인 복귀 경로로 허용한다', () => {
  assert.equal(sanitizeAuthReturnPath('/monitoring?cctv_no=12&event_no=4'), '/monitoring?cctv_no=12&event_no=4');
  assert.equal(createAuthReturnPath({ pathname: '/mypage', search: '?tab=activity' }), '/mypage?tab=activity');
});

test('외부 URL, 공개 경로, 알 수 없는 경로는 복귀 경로에서 제외한다', () => {
  assert.equal(sanitizeAuthReturnPath('https://example.com/admin'), null);
  assert.equal(sanitizeAuthReturnPath('//example.com/admin'), null);
  assert.equal(sanitizeAuthReturnPath('/login'), null);
  assert.equal(sanitizeAuthReturnPath('/unknown'), null);
});

test('역할 제한이 없으면 인증 사용자를 허용하고 관리자 경로는 admin만 허용한다', () => {
  assert.equal(hasAllowedRole({ role: 'user' }), true);
  assert.equal(hasAllowedRole({ role: 'admin' }, ['admin']), true);
  assert.equal(hasAllowedRole({ role: 'user' }, ['admin']), false);
});
