import { defineConfig } from 'vite';

export default defineConfig({
  // 상대 경로를 사용하도록 설정하여 GitHub Pages 하위 경로에서도 리소스가 정상적으로 로드되게 합니다.
  base: '/distribution/',
});
