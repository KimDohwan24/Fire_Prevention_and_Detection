import test from 'node:test';
import assert from 'node:assert/strict';
import {
  buildEventTrend,
  calculateTrendSummary,
  createDashboardMetrics,
} from './dashboardMetrics.js';

const localIso = (year, monthIndex, day, hour = 0, minute = 0) => (
  new Date(year, monthIndex, day, hour, minute).toISOString()
);

test('이번 달 1일부터 현재까지의 확정 화재만 집계한다', () => {
  const now = new Date(2026, 7, 22, 12, 0);
  const events = [
    {
      event_no: 1,
      event_status: 'CONFIRMED',
      event_first_detected_at: localIso(2026, 7, 1),
      event_is_test: false,
    },
    {
      event_no: 2,
      event_status: 'CONFIRMED',
      event_first_detected_at: localIso(2026, 7, 22, 11, 59),
      event_is_test: false,
    },
    {
      event_no: 3,
      event_status: 'CONFIRMED',
      event_first_detected_at: localIso(2026, 6, 31, 23, 59),
      event_is_test: false,
    },
    {
      event_no: 4,
      event_status: 'CONFIRMED',
      event_first_detected_at: localIso(2026, 7, 23),
      event_is_test: false,
    },
    {
      event_no: 5,
      event_status: 'CONFIRMED',
      event_first_detected_at: localIso(2026, 7, 10),
      event_is_test: true,
    },
    {
      event_no: 6,
      event_status: 'DISMISSED',
      event_first_detected_at: localIso(2026, 7, 12),
      event_is_test: false,
    },
  ];

  const metrics = createDashboardMetrics({ events, now });

  assert.deepEqual(metrics.confirmedThisMonth.map((event) => event.event_no), [2, 1]);
});

test('이번 달 119 신고의 전체·접수·실패 건수를 구분한다', () => {
  const now = new Date(2026, 7, 22, 12, 0);
  const reports = [
    { report_no: 1, report_status: 'DISPATCHED', reported_at: localIso(2026, 7, 1) },
    { report_no: 2, report_status: 'ACCEPTED', reported_at: localIso(2026, 7, 10) },
    { report_no: 3, report_status: 'FAILED', reported_at: localIso(2026, 7, 20) },
    { report_no: 4, report_status: 'SENDING', reported_at: localIso(2026, 7, 22, 11) },
    { report_no: 5, report_status: 'FAILED', reported_at: localIso(2026, 6, 31, 23, 59) },
    { report_no: 6, report_status: 'ACCEPTED', reported_at: localIso(2026, 7, 23) },
  ];

  const metrics = createDashboardMetrics({ reports, now });

  assert.equal(metrics.reportsThisMonth.length, 4);
  assert.equal(metrics.dispatchedReportsThisMonth.length, 2);
  assert.equal(metrics.failedReportsThisMonth.length, 1);
});

test('31일인 달에도 월초 사건을 포함한다', () => {
  const now = new Date(2026, 7, 31, 23, 59);
  const events = [{
    event_no: 1,
    event_status: 'CONFIRMED',
    event_first_detected_at: localIso(2026, 7, 1),
    event_is_test: false,
  }];

  const metrics = createDashboardMetrics({ events, now });

  assert.equal(metrics.confirmedThisMonth.length, 1);
});

test('calculateTrendSummary가 기간별 총 건수, 일평균, 최다 발생일을 정확히 계산한다', () => {
  const now = new Date(2026, 7, 22, 12, 0);
  const events = [
    { event_no: 1, event_class: 'FLAME', event_first_detected_at: localIso(2026, 7, 20), event_is_test: false },
    { event_no: 2, event_class: 'SMOKE', event_first_detected_at: localIso(2026, 7, 20), event_is_test: false },
    { event_no: 3, event_class: 'FLAME_SMOKE', event_first_detected_at: localIso(2026, 7, 22), event_is_test: false },
  ];

  const points7 = buildEventTrend(events, 7, now);
  assert.equal(points7.length, 7);

  const summary = calculateTrendSummary(points7);
  assert.equal(summary.total, 3);
  assert.equal(summary.average, '0.4');
  assert.equal(summary.peakCount, 2);
  assert.match(summary.peakLabel, /8\.20/);
});
