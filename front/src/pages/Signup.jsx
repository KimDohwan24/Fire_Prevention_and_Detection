import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { useDaumPostcodePopup } from 'react-daum-postcode';

const Signup = () => {
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
    gender: '',
    birthYear: '',
    birthMonth: '',
    birthDay: '',
  });

  const openPostcode = useDaumPostcodePopup();

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

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

    setFormData(prev => ({ ...prev, address: fullAddress }));
  };

  const handleSearchAddress = () => {
    openPostcode({ onComplete: handleCompletePostcode });
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    // TODO: Implement actual signup logic
    console.log(formData);
    alert('회원가입이 완료되었습니다.');
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
            파이어가드 회원가입
          </h1>
        </div>
      </div>

      <div className="w-full max-w-[420px]">
        <form className="space-y-5" onSubmit={handleSubmit}>
          
          {/* 아이디 */}
          <div className="flex flex-col space-y-1.5">
            <input
              type="text"
              name="id"
              value={formData.id}
              onChange={handleChange}
              className="w-full h-[40px] px-4 bg-canvas border border-hairline rounded-full text-body-md text-ink placeholder:text-mute focus:outline-none focus:border-ink transition-all"
              placeholder="아이디"
              required
            />
          </div>

          {/* 비밀번호 */}
          <div className="flex flex-col space-y-1.5">
            <input
              type="password"
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
            <input
              type="password"
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
          <div className="flex flex-col space-y-1.5 pt-1">
            <label className="text-body-sm-strong text-ink px-2">이메일</label>
            <div className="flex items-center space-x-2">
              <input
                type="text"
                name="emailId"
                value={formData.emailId}
                onChange={handleChange}
                className="flex-1 h-[40px] px-4 bg-canvas border border-hairline rounded-full text-body-md text-ink placeholder:text-mute focus:outline-none focus:border-ink transition-all w-0"
                placeholder="이메일"
                required
              />
              <span className="text-body-md text-ink flex-shrink-0">@</span>
              {formData.emailDomain === '직접입력' ? (
                <div className="flex items-center space-x-1.5 flex-1">
                  <input
                    type="text"
                    name="customDomain"
                    value={formData.customDomain}
                    onChange={handleChange}
                    className="flex-1 h-[40px] px-4 bg-canvas border border-hairline rounded-full text-body-md text-ink placeholder:text-mute focus:outline-none focus:border-ink transition-all w-0"
                    placeholder="도메인 (예: kakao.com)"
                    required
                    autoFocus
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
                      className="absolute inset-0 opacity-0 cursor-pointer w-full h-full"
                      title="도메인 선택"
                    >
                      <option value="직접입력">직접입력</option>
                      <option value="naver.com">naver.com</option>
                      <option value="gmail.com">gmail.com</option>
                      <option value="daum.net">daum.net</option>
                    </select>
                  </div>
                </div>
              ) : (
                <div className="relative flex-1">
                  <select
                    name="emailDomain"
                    value={formData.emailDomain}
                    onChange={handleChange}
                    className="w-full h-[40px] pl-4 pr-8 bg-canvas border border-hairline rounded-full text-body-md text-ink focus:outline-none focus:border-ink transition-all appearance-none cursor-pointer"
                    required
                  >
                    <option value="" disabled>선택해주세요</option>
                    <option value="naver.com">naver.com</option>
                    <option value="gmail.com">gmail.com</option>
                    <option value="daum.net">daum.net</option>
                    <option value="직접입력">직접입력</option>
                  </select>
                  <div className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none text-mute">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7"></path></svg>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* 휴대폰 */}
          <div className="flex flex-col space-y-1.5">
            <label className="text-body-sm-strong text-ink px-2">휴대폰</label>
            <div className="flex items-center space-x-2">
              <input
                type="text"
                name="phone"
                value={formData.phone}
                onChange={handleChange}
                className="flex-1 h-[40px] px-4 bg-canvas border border-hairline rounded-full text-body-md text-ink placeholder:text-mute focus:outline-none focus:border-ink transition-all w-0"
                placeholder="숫자만입력해주세요"
                required
              />
              <button
                type="button"
                className="h-[40px] px-5 bg-surface-soft border border-hairline text-ink rounded-full text-button-md whitespace-nowrap hover:bg-hairline active:scale-[0.98] transition-all flex-shrink-0"
              >
                인증요청
              </button>
            </div>
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
                className="flex-1 h-[40px] px-4 bg-surface-soft border border-hairline rounded-full text-body-md text-ink placeholder:text-mute focus:outline-none transition-all cursor-not-allowed w-0"
                placeholder="주소 검색 버튼을 눌러주세요"
                required
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
                  autoFocus
                />
              </div>
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

          <div className="pt-6 pb-2">
            <button
              type="submit"
              className="w-full h-[48px] bg-primary text-on-primary rounded-full text-button-md text-[16px] font-medium hover:bg-ink-deep active:scale-[0.98] transition-all duration-200"
            >
              회원가입
            </button>
          </div>
          
          <div className="text-center">
            <Link to="/login" className="text-body-sm text-body hover:text-ink underline decoration-hairline hover:decoration-ink underline-offset-4 transition-colors">
              이미 계정이 있으신가요?
            </Link>
          </div>
        </form>
      </div>
    </div>
  );
};

export default Signup;
