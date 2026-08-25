import test from 'node:test';
import assert from 'node:assert/strict';
import { findNearestAgency } from './nearestAgency.js';

test('CCTV와 가장 가까운 활성 소방서를 선택한다', () => {
  const nearest = findNearestAgency(
    { cctv_lat: 37.5665, cctv_lng: 126.9780 },
    [
      { agency_no: 10, agency_name: '먼 소방서', agency_lat: 37.58, agency_lng: 127.01 },
      { agency_no: 20, agency_name: '가까운 소방서', agency_lat: 37.567, agency_lng: 126.979 },
    ],
  );

  assert.equal(nearest.agency_no, 20);
  assert.equal(nearest.agency_name, '가까운 소방서');
  assert.ok(nearest.distance_km > 0);
});

test('비활성·좌표 누락 소방서는 예상 배정에서 제외한다', () => {
  const nearest = findNearestAgency(
    { lat: 37.5665, lng: 126.9780 },
    [
      { agency_no: 1, agency_name: '비활성 소방서', agency_is_active: false, agency_lat: 37.5666, agency_lng: 126.9781 },
      { agency_no: 2, agency_name: '좌표 없음 소방서', agency_lat: null, agency_lng: null },
      { agency_no: 3, agency_name: '사용 가능 소방서', agency_is_active: true, agency_lat: 37.568, agency_lng: 126.98 },
    ],
  );

  assert.equal(nearest.agency_no, 3);
});

test('CCTV 또는 소방서 좌표가 없으면 예상 배정을 만들지 않는다', () => {
  assert.equal(findNearestAgency({ cctv_lat: null, cctv_lng: null }, []), null);
  assert.equal(findNearestAgency({ cctv_lat: 37.5665, cctv_lng: 126.9780 }, [{ agency_no: 1 }]), null);
});
