import React, { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { oauthApi, SOCIAL_PROVIDERS } from '../api';

// 프로바이더가 사용자 거부 시 붙여 보내는 error 값들. 오류가 아니라 "취소"로 안내한다.
const USER_CANCELLED_ERRORS = ['access_denied', 'user_cancel', 'user_cancelled', 'consent_required'];

const OAuthCallback = () => {
  const navigate = useNavigate();
  const { provider } = useParams();
  const [searchParams] = useSearchParams();
  // 'loading' | 'cancelled' | 'error' — 성공하면 곧바로 /dashboard 로 떠나므로 상태가 없다.
  const [status, setStatus] = useState('loading');
  const [message, setMessage] = useState('');

  // 인가 코드는 일회용이라 두 번 교환하면 두 번째가 반드시 실패한다.
  // StrictMode 가 useEffect 를 두 번 돌리므로 ref 로 첫 실행만 통과시킨다.
  const exchangedRef = useRef(false);

  useEffect(() => {
    if (exchangedRef.current) return;
    exchangedRef.current = true;

    const fail = (kind, text) => {
      setStatus(kind);
      setMessage(text);
    };

    const providerLabel = SOCIAL_PROVIDERS.find((p) => p.id === provider)?.name || provider;

    const run = async () => {
      const errorParam = searchParams.get('error');
      const code = searchParams.get('code');
      const state = searchParams.get('state');

      // state 는 결과와 무관하게 항상 회수해서 지운다 — 남겨두면 다음 시도에 재사용된다.
      const savedState = oauthApi.takeState(provider);

      if (!SOCIAL_PROVIDERS.some((p) => p.id === provider)) {
        fail('error', '지원하지 않는 소셜 로그인입니다.');
        return;
      }

      if (errorParam) {
        if (USER_CANCELLED_ERRORS.includes(errorParam)) {
          fail('cancelled', `${providerLabel} 로그인을 취소하셨습니다.`);
        } else {
          fail('error', `${providerLabel} 인증 중 문제가 발생했습니다. (${errorParam})`);
        }
        return;
      }

      if (!code) {
        fail('error', '인증 정보가 전달되지 않았습니다. 로그인을 다시 시도해주세요.');
        return;
      }

      if (!savedState || savedState !== state) {
        fail('error', '보안 검증에 실패했습니다. 로그인 화면에서 다시 시도해주세요.');
        return;
      }

      try {
        await oauthApi.login(provider, code, state);
        navigate('/dashboard', { replace: true });
      } catch (err) {
        console.error('소셜 로그인 실패:', err);
        // 계정 상태 문제는 재시도해도 소용없으므로 원인을 그대로 알려준다.
        const byCode = {
          UNSUPPORTED_PROVIDER: '지원하지 않는 소셜 로그인입니다.',
          OAUTH_NOT_CONFIGURED: '해당 소셜 로그인이 아직 설정되지 않았습니다. 관리자에게 문의해주세요.',
          INVALID_OAUTH_STATE: '보안 검증에 실패했습니다. 로그인 화면에서 다시 시도해주세요.',
          OAUTH_PROVIDER_ERROR: `${providerLabel} 서버와 통신하지 못했습니다. 잠시 후 다시 시도해주세요.`,
          ACCOUNT_SUSPENDED: '정지된 계정입니다. 관리자에게 문의해주세요.',
          ACCOUNT_WITHDRAWN: '탈퇴한 계정입니다. 관리자에게 문의해주세요.',
        };
        fail('error', byCode[err.code] || err.message || '소셜 로그인에 실패했습니다.');
      }
    };

    run();
  }, [navigate, provider, searchParams]);

  return (
    <div className="min-h-screen bg-canvas flex flex-col items-center justify-center px-4 font-ui transition-colors duration-300">
      <div className="w-full max-w-[360px] flex flex-col items-center text-center">
        <div className="text-[40px] leading-none mb-6">🔥</div>

        {status === 'loading' ? (
          <>
            <div className="w-6 h-6 mb-4 rounded-full border-2 border-hairline border-t-ink animate-spin" />
            <p className="text-body-md text-ink">로그인 처리 중입니다...</p>
            <p className="mt-2 text-body-sm text-mute">잠시만 기다려주세요.</p>
          </>
        ) : (
          <>
            <h1 className="text-heading-lg font-medium text-ink mb-2">
              {status === 'cancelled' ? '로그인이 취소되었습니다' : '로그인에 실패했습니다'}
            </h1>
            <p className="text-body-sm text-body">{message}</p>
            <Link
              to="/"
              className="mt-8 w-full h-[36px] bg-primary text-on-primary rounded-full text-button-md flex items-center justify-center hover:bg-ink-deep active:scale-[0.98] transition-all duration-200"
            >
              로그인 화면으로 돌아가기
            </Link>
          </>
        )}
      </div>
    </div>
  );
};

export default OAuthCallback;
