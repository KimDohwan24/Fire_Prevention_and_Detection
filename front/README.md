# 화재 예방 및 탐지 시스템 - 프런트엔드 (Front-end)

이 프로젝트는 React + Vite 기반으로 구축된 웹 대시보드 프런트엔드입니다.

---

## 📦 의존성 라이브러리 일괄 설치 (requirements.txt와 동일한 기능)

파이썬 백엔드의 `pip install -r requirements.txt`와 마찬가지로, Node.js 환경에서는 **`package.json`** 파일이 모든 라이브러리의 명세를 관리합니다.

프로젝트 루트 폴더에서 아래 명령어를 실행하면 `package.json`에 등록된 모든 프런트엔드 라이브러리가 **한 번에 한꺼번에 설치**됩니다:

```bash
npm install
```

> **Note (Windows PowerShell 권한 이슈 발생 시):**
> ```cmd
> cmd /c npm install
> ```

---

## 🛠 설치되는 주요 라이브러리 목록 (`package.json`)

* **Core**: `react`, `react-dom`
* **Routing**: `react-router-dom`
* **Icons**: `lucide-react`
* **Address Search**: `react-daum-postcode`
* **Styling**: `tailwindcss`, `@tailwindcss/vite`
* **Build Tool**: `vite`, `@vitejs/plugin-react`

---

## 🚀 프런트엔드 개발 서버 실행

```bash
npm run dev
# 또는 Windows PowerShell: cmd /c npm run dev
```

