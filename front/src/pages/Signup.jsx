import React, { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useDaumPostcodePopup } from 'react-daum-postcode';

import { userApi, authApi } from '../api';
import PasswordInput from '../components/PasswordInput';
import PrivacyConsentModal from '../components/PrivacyConsentModal';

const EMAIL_VERIFICATION_DURATION = 5 * 60;
const ADDRESS_REQUIRED_MESSAGE = '주소 검색을 완료해주세요.';
const PRIVACY_CONSENT_REQUIRED_MESSAGE = '개인정보 수집·이용 동의 항목을 체크해야 회원가입을 진행할 수 있습니다.';

const Signup = () => {
  const navigate = useNavigate();
  const [formData, setFormData] = useState({
    id: '',
    password: '',
    passwordConfirm: '',
    name: '',
    emailId: '',
    emailDomain: '',
    customDomain: '',
    phone: '',
    address: '',
    detailAddress: '',
    gender: '선택안함',
    birthYear: '',
    birthMonth: '',
    birthDay: '',
  });
  const [errorMsg, setErrorMsg] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isIdChecked, setIsIdChecked] = useState(false);
  const [checkedUserId, setCheckedUserId] = useState('');
  const [isIdChecking, setIsIdChecking] = useState(false);
  const [idCheckMessage, setIdCheckMessage] = useState('');
  const [isEmailVerificationRequested, setIsEmailVerificationRequested] = useState(false);
  const [isEmailVerificationConfirmed, setIsEmailVerificationConfirmed] = useState(false);
  const [emailVerificationTimeLeft, setEmailVerificationTimeLeft] = useState(EMAIL_VERIFICATION_DURATION);
  const [emailVerificationCode, setEmailVerificationCode] = useState('');
  const [addressErrorMsg, setAddressErrorMsg] = useState('');
  const [isPrivacyConsentChecked, setIsPrivacyConsentChecked] = useState(false);
  const [isPrivacyConsentModalOpen, setIsPrivacyConsentModalOpen] = useState(false);
  const [privacyConsentError, setPrivacyConsentError] = useState(false);

  const openPostcode = useDaumPostcodePopup();

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const handleIdChange = (e) => {
    const { value } = e.target;
    setFormData(prev => ({ ...prev, id: value }));

    if (value.trim() !== checkedUserId) {
      setIsIdChecked(false);
      setCheckedUserId('');
      setIdCheckMessage('');
    }
  };

  const handleCheckId = async () => {
    const userId = formData.id.trim();

    setErrorMsg('');
    setIsIdChecked(false);
    setCheckedUserId('');
    setIdCheckMessage('');

    if (!userId) {
      setIdCheckMessage('아이디를 입력해주세요.');
      return;
    }

    setIsIdChecking(true);
    try {
      const response = await authApi.checkUserId(userId);

      if (response?.available === false) {
        setIdCheckMessage('중복된 아이디입니다.');
        return;
      }

      if (response?.available !== true) {
        throw new Error('아이디 중복확인 응답을 확인할 수 없습니다.');
      }

      setCheckedUserId(userId);
      setIsIdChecked(true);
      setIdCheckMessage('사용 가능한 아이디입니다.');
    } catch (err) {
      console.error('아이디 중복확인 실패:', err);
      setCheckedUserId('');
      
      // 💡 [수정] 백엔드가 400 에러와 함께 보낸 {"detail": "..."} 메시지를 꺼내오도록 변경!
      const errorMsg = err.response?.data?.detail || err.message || '아이디 중복확인에 실패했습니다.';
      setIdCheckMessage(errorMsg);
      
    } finally {
      setIsIdChecking(false);
    }
  };

  const handlePhoneChange = (e) => {
    setFormData(prev => ({
      ...prev,
      phone: e.target.value.replace(/[^0-9]/g, '').slice(0, 11),
    }));
  };

  useEffect(() => {
    if (!isEmailVerificationRequested || emailVerificationTimeLeft <= 0) {
      return undefined;
    }

    const timerId = window.setInterval(() => {
      setEmailVerificationTimeLeft(prevTime => Math.max(prevTime - 1, 0));
    }, 1000);

    return () => window.clearInterval(timerId);
  }, [isEmailVerificationRequested, emailVerificationTimeLeft]);

  // const handleRequestEmailVerification = () => {
  //   setErrorMsg('');
  //   setIsEmailVerificationRequested(true);
  //   setEmailVerificationTimeLeft(EMAIL_VERIFICATION_DURATION);
  //   setEmailVerificationCode('');
  // };
const handleRequestEmailVerification = async () => {
  setErrorMsg('');

  const emailId = formData.emailId ? formData.emailId.trim() : '';
  // const emailDomainStr = formData.emailDomain === '직접입력' ? formData.customDomain : formData.emailDomain;
  // const fullEmail = formData.emailId && emailDomainStr ? `${formData.emailId}@${emailDomainStr}` : null;

  const emailDomainStr = formData.emailDomain === '직접입력' 
    ? (formData.customDomain ? formData.customDomain.trim() : '') 
    : formData.emailDomain;

    // 2. 둘 중 하나라도 비어있거나, 입력값 내부에 공백이 포함되어 있는지 확인
  if (!emailId || !emailDomainStr || /\s/.test(emailId) || /\s/.test(emailDomainStr)) {
    setErrorMsg('이메일 아이디와 도메인에 공백을 포함할 수 없습니다.');
    return;
  }
  // if (!fullEmail) {
  //   setErrorMsg('이메일을 올바르게 입력해주세요.');
  //   return;
  // }


  // 3. 직접입력인 경우 도메인에 마침표(.)가 포함되어 있는지, 그리고 양 끝이 점이 아닌지 검증
if (formData.emailDomain === '직접입력') {
    const hasDot = emailDomainStr.includes('.');
    const isValidDotPosition = !emailDomainStr.startsWith('.') && !emailDomainStr.endsWith('.');
    
    if (!hasDot || !isValidDotPosition) {
        setErrorMsg('올바른 이메일 도메인 형식(예: domain.com)을 입력해주세요.');
        return;
    }
}

  // 4. 최종 전체 이메일 조합 및 정규식 검증
  const fullEmail = `${emailId}@${emailDomainStr}`;
  const emailRegex = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;

  if (!emailRegex.test(fullEmail)) {
    setErrorMsg('이메일 형식에 맞게 올바르게 입력해주세요.');
    return;
  }

  try {
    await authApi.requestEmailVerify(fullEmail);

    setIsEmailVerificationRequested(true);
    setIsEmailVerificationConfirmed(false);
    setEmailVerificationTimeLeft(EMAIL_VERIFICATION_DURATION);
    setEmailVerificationCode('');
    alert('인증번호가 발송되었습니다.');
  } catch (err) {
    console.error('이메일 전송 실패:', err);
    setErrorMsg(err.message || '이메일 전송에 실패했습니다.');
  }
};

  const handleConfirmEmailVerification = async () => {
    if (emailVerificationTimeLeft <= 0) {
      setErrorMsg('인증 시간이 만료되었습니다. 인증번호를 다시 요청해주세요.');
      return;
    }

    if (emailVerificationCode.length !== 6) {
      setErrorMsg('인증번호 6자리를 입력해주세요.');
      return;
    }

    setErrorMsg('');

    // 이메일 문자열 조합
    const emailId = formData.emailId ? formData.emailId.trim() : '';
    // const emailDomainStr = formData.emailDomain === '직접입력' ? formData.customDomain : formData.emailDomain;
    const emailDomainStr = formData.emailDomain === '직접입력' 
      ? (formData.customDomain ? formData.customDomain.trim() : '') 
      : formData.emailDomain;
    const fullEmail = `${formData.emailId}@${emailDomainStr}`;

    try {
      // 📌 백엔드의 /verify-code API 호출
      const response = await fetch("http://localhost:5000/api/auth/verify-code", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 
        email: fullEmail, 
        code: emailVerificationCode 
        })
      });

      const data = await response.json();

      if (!response.ok) {
        setErrorMsg(data.error || '인증번호가 일치하지 않습니다.');
        return;
      }

      // 검증 성공 시
      setIsEmailVerificationConfirmed(true);
      alert('이메일 인증이 완료되었습니다.');

    } catch (err) {
      console.error('인증 확인 실패:', err);
      setErrorMsg('서버 통신 중 오류가 발생했습니다.');
    }
  };

  const formattedEmailVerificationTime = `${String(Math.floor(emailVerificationTimeLeft / 60)).padStart(2, '0')}:${String(emailVerificationTimeLeft % 60).padStart(2, '0')}`;

  const handleCompletePostcode = (data) => {
    let fullAddress = data.address;
    let extraAddress = '';

    if (data.addressType === 'R') {
      if (data.bname !== '') {
        extraAddress += data.bname;
      }
      if (data.buildingName !== '') {
        extraAddress += extraAddress !== '' ? `, ${data.buildingName}` : data.buildingName;
      }
      fullAddress += extraAddress !== '' ? ` (${extraAddress})` : '';
    }

    setAddressErrorMsg('');
    setErrorMsg((previousMessage) => (
      previousMessage === ADDRESS_REQUIRED_MESSAGE ? '' : previousMessage
    ));
    setFormData(prev => ({ ...prev, address: fullAddress }));
  };

  const handleSearchAddress = () => {
    openPostcode({ onComplete: handleCompletePostcode });
  };

  const validateAddress = () => {
    if (formData.address.trim()) {
      setAddressErrorMsg('');
      return true;
    }

    setAddressErrorMsg(ADDRESS_REQUIRED_MESSAGE);
    setErrorMsg(ADDRESS_REQUIRED_MESSAGE);
    return false;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrorMsg('');

    if (!isPrivacyConsentChecked) {
      setPrivacyConsentError(true);
      setErrorMsg(PRIVACY_CONSENT_REQUIRED_MESSAGE);
      return;
    }

    setPrivacyConsentError(false);

    if (!validateAddress()) {
      return;
    }

    if (!isIdChecked || checkedUserId !== formData.id.trim()) {
      setErrorMsg('아이디 중복확인을 완료해주세요.');
      return;
    }

    if (formData.password !== formData.passwordConfirm) {
      setErrorMsg('비밀번호와 비밀번호 확인이 일치하지 않습니다.');
      return;
    }
    if (!isEmailVerificationConfirmed) {
      setErrorMsg('이메일 인증을 완료해주세요.');
      return;
    }

    const address = formData.address.trim();
    const emailDomainStr = formData.emailDomain === 'type' ? formData.customDomain : formData.emailDomain;
    const fullEmail = formData.emailId && emailDomainStr ? `${formData.emailId}@${emailDomainStr}` : null;
    const rawPhone = formData.phone.replace(/[^0-9]/g, '');
    const detailAddress = formData.detailAddress.trim();

    setIsLoading(true);
    try {
      await userApi.create({
        user_id: formData.id.trim(),
        user_pw: formData.password,
        user_name: formData.name.trim(),
        user_role: 'VIEWER',
        user_email: fullEmail,
        user_phone: rawPhone || null,
        user_gender: formData.gender || null,
        user_address: [address, detailAddress].filter(Boolean).join(' '),
      });
      alert('회원가입이 완료되었습니다. 로그인 해주세요.');
      navigate('/login');
    } catch (err) {
      console.error('회원가입 실패:', err);
      if (err.status === 409 || err.code === 'DUPLICATE_USER_ID') {
        setIsIdChecked(false);
        setCheckedUserId('');
        setIdCheckMessage('중복된 아이디입니다.');
      }
      setErrorMsg(err.message || '회원가입에 실패했습니다.');
    } finally {
      setIsLoading(false);
    }
  };

  // Generate options for birthdate
  const years = Array.from({ length: 100 }, (_, i) => new Date().getFullYear() - i);
  const months = Array.from({ length: 12 }, (_, i) => i + 1);
  const days = Array.from({ length: 31 }, (_, i) => i + 1);

  return (
    <div className="min-h-screen bg-canvas flex flex-col items-center pt-24 pb-24 px-4 font-ui relative transition-colors duration-300">

      {/* Brand / Logo */}
      <div className="flex flex-row items-center space-x-5 mb-10">
        <div className="text-[48px] leading-none">🔥</div>
        <div className="flex flex-col">
          <h1 className="font-display text-display-lg font-medium text-ink tracking-tight mb-1">
            FireGuard 회원가입
          </h1>
        </div>
      </div>

      <div className="w-full max-w-[420px]">
        <form className="space-y-5" onSubmit={handleSubmit}>
          {errorMsg && (
            <div role="alert" aria-live="assertive" className="p-3 bg-red-500/10 border border-red-500/30 rounded-xl text-red-500 text-xs font-semibold text-center">
              {errorMsg}
            </div>
          )}

          {/* 아이디 */}
          <div className="flex flex-col space-y-1.5">
            <div className="flex items-center gap-2">
              <input
                type="text"
                name="id"
                value={formData.id}
                onChange={handleIdChange}
                className="min-w-0 flex-1 h-[40px] px-4 bg-canvas border border-hairline rounded-full text-body-md text-ink placeholder:text-mute focus:outline-none focus:border-ink transition-all"
                placeholder="아이디"
                autoComplete="username"
                required
              />
              <button
                type="button"
                onClick={handleCheckId}
                disabled={isIdChecking}
                className="h-[40px] flex-shrink-0 px-4 bg-surface-soft border border-hairline text-ink rounded-full text-button-md whitespace-nowrap hover:bg-hairline active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50 transition-all"
              >
                {isIdChecking ? '확인 중...' : '중복확인'}
              </button>
            </div>
            {idCheckMessage && (
              <p
                className={`px-2 text-caption-sm ${isIdChecked ? 'text-emerald-600' : 'text-red-500'}`}
                role="status"
                aria-live="polite"
              >
                {idCheckMessage}
              </p>
            )}
          </div>

          {/* 비밀번호 */}
          <div className="flex flex-col space-y-1.5">
            <PasswordInput
              name="password"
              value={formData.password}
              onChange={handleChange}
              className="w-full h-[40px] px-4 bg-canvas border border-hairline rounded-full text-body-md text-ink placeholder:text-mute focus:outline-none focus:border-ink transition-all"
              placeholder="비밀번호"
              required
            />
          </div>

          {/* 비밀번호 확인 */}
          <div className="flex flex-col space-y-1.5">
            <PasswordInput
              name="passwordConfirm"
              value={formData.passwordConfirm}
              onChange={handleChange}
              className="w-full h-[40px] px-4 bg-canvas border border-hairline rounded-full text-body-md text-ink placeholder:text-mute focus:outline-none focus:border-ink transition-all"
              placeholder="비밀번호 확인"
              required
            />
          </div>

          {/* 이름 */}
          <div className="flex flex-col space-y-1.5">
            <input
              type="text"
              name="name"
              value={formData.name}
              onChange={handleChange}
              className="w-full h-[40px] px-4 bg-canvas border border-hairline rounded-full text-body-md text-ink placeholder:text-mute focus:outline-none focus:border-ink transition-all"
              placeholder="이름"
              required
            />
          </div>

          {/* 이메일 */}
          <div className="flex flex-col space-y-1.5">
            <label className="text-body-sm-strong text-ink px-2">이메일</label>
            <div className="flex items-center gap-2">
              <input
                type="text"
                name="emailId"
                value={formData.emailId}
                onChange={handleChange}
                className="min-w-0 flex-1 h-[40px] px-4 bg-canvas border border-hairline rounded-full text-body-md text-ink placeholder:text-mute focus:outline-none focus:border-ink transition-all"
                placeholder="이메일"
                required
              />
              <span className="text-body-md text-ink flex-shrink-0">@</span>
              {formData.emailDomain === '직접입력' ? (
                <div className="min-w-0 flex flex-1 items-center gap-1.5">
                  <input
                    type="text"
                    name="customDomain"
                    value={formData.customDomain}
                    onChange={handleChange}
                    className="min-w-0 flex-1 h-[40px] px-4 bg-canvas border border-hairline rounded-full text-body-md text-ink placeholder:text-mute focus:outline-none focus:border-ink transition-all"
                    placeholder="도메인 (예: kakao.com)"
                    required
                  />
                  <div className="relative w-[40px] h-[40px] flex-shrink-0">
                    <div className="w-full h-full rounded-full border border-hairline bg-surface-soft text-ink flex items-center justify-center pointer-events-none hover:bg-hairline transition-all">
                      <svg className="w-4 h-4 text-ink" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7"></path>
                      </svg>
                    </div>
                    <select
                      name="emailDomain"
                      value={formData.emailDomain}
                      onChange={(e) => {
                        const val = e.target.value;
                        setFormData(prev => ({
                          ...prev,
                          emailDomain: val,
                          customDomain: val === '직접입력' ? prev.customDomain : ''
                        }));
                      }}
                      className="absolute inset-0 w-full h-full cursor-pointer bg-canvas text-ink opacity-0"
                      style={{ color: '#000000', backgroundColor: '#ffffff', colorScheme: 'light' }}
                      title="도메인 선택"
                    >
                      <option className="bg-canvas text-ink" value="직접입력">직접입력</option>
                      <option className="bg-canvas text-ink" value="naver.com">naver.com</option>
                      <option className="bg-canvas text-ink" value="gmail.com">gmail.com</option>
                      <option className="bg-canvas text-ink" value="daum.net">daum.net</option>
                    </select>
                  </div>
                </div>
              ) : (
                <div className="relative min-w-0 flex-1">
                  <select
                    name="emailDomain"
                    value={formData.emailDomain}
                    onChange={handleChange}
                    className="w-full h-[40px] pl-4 pr-8 bg-canvas border border-hairline rounded-full text-body-md text-ink focus:outline-none focus:border-ink transition-all appearance-none cursor-pointer"
                    style={{ color: '#000000', backgroundColor: '#ffffff', colorScheme: 'light' }}
                    required
                  >
                    <option className="bg-canvas text-ink" value="" disabled>선택해주세요</option>
                    <option className="bg-canvas text-ink" value="naver.com">naver.com</option>
                    <option className="bg-canvas text-ink" value="gmail.com">gmail.com</option>
                    <option className="bg-canvas text-ink" value="daum.net">daum.net</option>
                    <option className="bg-canvas text-ink" value="직접입력">직접입력</option>
                  </select>
                  <div className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none text-mute">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7"></path></svg>
                  </div>
                </div>
              )}
            </div>

            <div className="flex items-center justify-between gap-3 pt-1">
              <p className="text-caption-sm text-body">입력한 이메일로 인증번호를 보내요.</p>
              <button
                type="button"
                onClick={handleRequestEmailVerification}
                className="h-[40px] flex-shrink-0 px-5 bg-surface-soft border border-hairline text-ink rounded-full text-button-md whitespace-nowrap hover:bg-hairline active:scale-[0.98] transition-all"
              >
                인증요청
              </button>
            </div>

            {isEmailVerificationRequested && (
              <div className="mt-1 space-y-2 rounded-2xl border border-hairline bg-surface-soft p-3 animate-fadeIn">
                <div className="flex items-center justify-between px-1 text-caption-sm">
                  <span className="text-body">인증번호가 이메일로 발송되었습니다.</span>
                  <span className={`font-mono font-semibold ${emailVerificationTimeLeft === 0 ? 'text-mute' : 'text-red-500'}`} aria-live="polite">
                    {formattedEmailVerificationTime}
                  </span>
                </div>

                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    value={emailVerificationCode}
                    onChange={(e) => {
                      setEmailVerificationCode(e.target.value.replace(/[^0-9]/g, '').slice(0, 6));
                      setIsEmailVerificationConfirmed(false);
                    }}
                    className="min-w-0 flex-1 h-[40px] px-4 bg-canvas border border-hairline rounded-full text-body-md text-ink placeholder:text-mute focus:outline-none focus:border-ink transition-all"
                    placeholder="이메일 인증번호 6자리"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    maxLength={6}
                  />
                  <button
                    type="button"
                    onClick={handleRequestEmailVerification}
                    className="h-[40px] px-5 bg-surface-soft border border-hairline text-ink rounded-full text-button-md whitespace-nowrap hover:bg-hairline active:scale-[0.98] transition-all flex-shrink-0"
                  >
                    재전송
                  </button>
                </div>

                <button
                  type="button"
                  onClick={handleConfirmEmailVerification}
                  disabled={emailVerificationCode.length !== 6 || emailVerificationTimeLeft === 0}
                  className={`w-full h-[40px] rounded-full text-button-md transition-all ${
                    isEmailVerificationConfirmed
                      ? 'bg-emerald-500/10 border border-emerald-500/30 text-emerald-600'
                      : 'bg-primary text-on-primary hover:bg-ink-deep active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50'
                  }`}
                >
                  {isEmailVerificationConfirmed ? '인증 완료' : '인증번호 확인'}
                </button>
              </div>
            )}
          </div>

          {/* 휴대폰 */}
          <div className="flex flex-col space-y-1.5">
            <label className="text-body-sm-strong text-ink px-2">휴대폰</label>
            <input
              type="text"
              name="phone"
              value={formData.phone}
              onChange={handlePhoneChange}
              className="w-full h-[40px] px-4 bg-canvas border border-hairline rounded-full text-sm text-ink placeholder:text-xs placeholder:text-mute focus:outline-none focus:border-ink transition-all"
              placeholder="- 없이 숫자만 입력해주세요"
              inputMode="numeric"
              maxLength={11}
              required
            />
          </div>

          {/* 주소 */}
          <div className="flex flex-col space-y-1.5">
            <label className="text-body-sm-strong text-ink px-2">주소</label>
            <div className="flex items-center space-x-2">
              <input
                type="text"
                name="address"
                value={formData.address}
                readOnly
                className={`flex-1 h-[40px] px-4 bg-surface-soft border rounded-full text-body-md text-ink placeholder:text-mute focus:outline-none transition-all cursor-not-allowed w-0 ${addressErrorMsg ? 'border-red-500' : 'border-hairline'}`}
                placeholder="주소 검색 버튼을 눌러주세요"
                required
                aria-required="true"
                aria-invalid={Boolean(addressErrorMsg)}
              />
              <button
                type="button"
                onClick={handleSearchAddress}
                className="h-[40px] px-5 bg-surface-soft border border-hairline text-ink rounded-full text-button-md whitespace-nowrap hover:bg-hairline active:scale-[0.98] transition-all flex-shrink-0"
              >
                주소 검색
              </button>
            </div>

            {/* 상세 주소 (주소가 입력되었을 때 동적으로 나타남) */}
            {formData.address && (
              <div className="pt-1 animate-fadeIn">
                <input
                  type="text"
                  name="detailAddress"
                  value={formData.detailAddress}
                  onChange={handleChange}
                  className="w-full h-[40px] px-4 bg-canvas border border-hairline rounded-full text-body-md text-ink placeholder:text-mute focus:outline-none focus:border-ink transition-all"
                  placeholder="상세 주소를 입력해주세요 (예: 101동 202호)"
                />
              </div>
            )}
            {addressErrorMsg && (
              <p role="alert" aria-live="polite" className="px-2 text-caption-sm font-semibold text-red-500">
                {addressErrorMsg}
              </p>
            )}
          </div>

          {/* 성별 */}
          <div className="flex flex-col space-y-2 pt-2">
            <label className="text-body-sm-strong text-ink px-2">성별</label>
            <div className="flex items-center space-x-6 px-2">
              <label className="flex items-center space-x-2 cursor-pointer group">
                <div className={`w-4 h-4 rounded-full border flex items-center justify-center transition-all ${formData.gender === '남자' ? 'border-primary bg-primary' : 'border-hairline-strong group-hover:border-ink'}`}>
                  {formData.gender === '남자' && <div className="w-1.5 h-1.5 bg-canvas rounded-full"></div>}
                </div>
                <input type="radio" name="gender" value="남자" checked={formData.gender === '남자'} onChange={handleChange} className="hidden" required />
                <span className="text-body-md text-ink">남자</span>
              </label>
              <label className="flex items-center space-x-2 cursor-pointer group">
                <div className={`w-4 h-4 rounded-full border flex items-center justify-center transition-all ${formData.gender === '여자' ? 'border-primary bg-primary' : 'border-hairline-strong group-hover:border-ink'}`}>
                  {formData.gender === '여자' && <div className="w-1.5 h-1.5 bg-canvas rounded-full"></div>}
                </div>
                <input type="radio" name="gender" value="여자" checked={formData.gender === '여자'} onChange={handleChange} className="hidden" />
                <span className="text-body-md text-ink">여자</span>
              </label>
              <label className="flex items-center space-x-2 cursor-pointer group">
                <div className={`w-4 h-4 rounded-full border flex items-center justify-center transition-all ${formData.gender === '선택안함' ? 'border-primary bg-primary' : 'border-hairline-strong group-hover:border-ink'}`}>
                  {formData.gender === '선택안함' && <div className="w-1.5 h-1.5 bg-canvas rounded-full"></div>}
                </div>
                <input type="radio" name="gender" value="선택안함" checked={formData.gender === '선택안함'} onChange={handleChange} className="hidden" />
                <span className="text-body-md text-ink">선택안함</span>
              </label>
            </div>
          </div>

          {/* 생년월일 */}
          <div className="flex flex-col space-y-1.5 pt-2">
            <label className="text-body-sm-strong text-ink px-2">생년월일</label>
            <div className="flex items-center space-x-2">
              <div className="relative flex-1">
                <select
                  name="birthYear"
                  value={formData.birthYear}
                  onChange={handleChange}
                  className="w-full h-[40px] pl-4 pr-8 bg-canvas border border-hairline rounded-full text-body-md text-ink focus:outline-none focus:border-ink transition-all appearance-none"
                  required
                >
                  <option value="" disabled>년</option>
                  {years.map(y => <option key={y} value={y}>{y}</option>)}
                </select>
                <div className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none text-mute">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7"></path></svg>
                </div>
              </div>

              <div className="relative flex-1">
                <select
                  name="birthMonth"
                  value={formData.birthMonth}
                  onChange={handleChange}
                  className="w-full h-[40px] pl-4 pr-8 bg-canvas border border-hairline rounded-full text-body-md text-ink focus:outline-none focus:border-ink transition-all appearance-none"
                  required
                >
                  <option value="" disabled>월</option>
                  {months.map(m => <option key={m} value={m}>{m}</option>)}
                </select>
                <div className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none text-mute">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7"></path></svg>
                </div>
              </div>

              <div className="relative flex-1">
                <select
                  name="birthDay"
                  value={formData.birthDay}
                  onChange={handleChange}
                  className="w-full h-[40px] pl-4 pr-8 bg-canvas border border-hairline rounded-full text-body-md text-ink focus:outline-none focus:border-ink transition-all appearance-none"
                  required
                >
                  <option value="" disabled>일</option>
                  {days.map(d => <option key={d} value={d}>{d}</option>)}
                </select>
                <div className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none text-mute">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7"></path></svg>
                </div>
              </div>
            </div>
          </div>

          {/* 개인정보 수집·이용 동의 */}
          <div className="rounded-2xl border border-hairline bg-surface-soft p-4">
            <div className="flex items-start gap-3">
              <input
                id="privacy-consent"
                type="checkbox"
                checked={isPrivacyConsentChecked}
                onChange={(event) => {
                  const isChecked = event.target.checked;
                  setIsPrivacyConsentChecked(isChecked);
                  if (isChecked) {
                    setPrivacyConsentError(false);
                    if (errorMsg === PRIVACY_CONSENT_REQUIRED_MESSAGE) {
                      setErrorMsg('');
                    }
                  }
                }}
                className="mt-1 h-5 w-5 shrink-0 cursor-pointer accent-primary focus:outline-none focus-visible:outline-none"
                aria-describedby={privacyConsentError
                  ? 'privacy-consent-description privacy-consent-error'
                  : 'privacy-consent-description'}
                aria-invalid={privacyConsentError}
              />
              <div className="min-w-0 flex-1">
                <label htmlFor="privacy-consent" className="block cursor-pointer text-body-sm-strong text-ink">
                  <span className="mr-1 text-mute">[필수]</span>
                  개인정보 수집·이용에 동의합니다.
                </label>
                <p id="privacy-consent-description" className="mt-1 text-caption-sm leading-5 text-body">
                  회원가입과 서비스 운영을 위해 개인정보를 수집·이용합니다.
                </p>
                <button
                  type="button"
                  onClick={() => setIsPrivacyConsentModalOpen(true)}
                  className="mt-2 text-caption-sm text-body underline decoration-hairline underline-offset-4 transition-colors hover:text-ink focus:outline-none focus-visible:outline-none"
                >
                  자세히 보기
                </button>
              </div>
            </div>
            {privacyConsentError && (
              <p
                id="privacy-consent-error"
                role="alert"
                className="mt-3 px-2 text-caption-sm font-semibold text-red-500"
              >
                {PRIVACY_CONSENT_REQUIRED_MESSAGE}
              </p>
            )}
          </div>

          <div className="pt-6 pb-2">
            <button
              type="submit"
              onClick={(event) => {
                if (!isPrivacyConsentChecked) {
                  event.preventDefault();
                  setPrivacyConsentError(true);
                  setErrorMsg(PRIVACY_CONSENT_REQUIRED_MESSAGE);
                  document.getElementById('privacy-consent')?.focus();
                  return;
                }

                if (!validateAddress()) {
                  event.preventDefault();
                }
              }}
              disabled={isLoading || isIdChecking}
              className="w-full h-[48px] bg-primary text-on-primary rounded-full text-button-md text-[16px] font-medium hover:bg-ink-deep active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50 transition-all duration-200"
            >
              {isLoading ? '가입 중...' : '회원가입'}
            </button>
          </div>

          <div className="text-center">
            <Link to="/login" className="text-body-sm text-body hover:text-ink underline decoration-hairline hover:decoration-ink underline-offset-4 transition-colors">
              이미 계정이 있으신가요?
            </Link>
          </div>
        </form>
      </div>

      <PrivacyConsentModal
        isOpen={isPrivacyConsentModalOpen}
        onClose={() => setIsPrivacyConsentModalOpen(false)}
      />
    </div>
  );
};

export default Signup;
