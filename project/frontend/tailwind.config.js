/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // 暖墨灰：覆盖默认 slate，让全站灰色统一带纸感暖调
        slate: {
          50: '#f7f5f0',
          100: '#efebe1',
          200: '#e3ded1',
          300: '#cfc8b8',
          400: '#a29c8c',
          500: '#7d7768',
          600: '#5c574b',
          700: '#45413a',
          800: '#33312b',
          900: '#27251e',
        },
        // 品牌色：墨藏青——学术与图书馆的经典色，替代默认蓝
        brand: {
          50: '#eef3f7',
          100: '#dce5ee',
          200: '#b3c4d6',
          300: '#7593b3',
          400: '#47688f',
          500: '#2c4c74',
          600: '#1f3a5f',
          700: '#16293f',
          800: '#122032',
          900: '#0e1826',
        },
        // 印章朱：只用于引用角标 [n] 与关键标记，是「可溯源」的视觉签名
        seal: {
          50: '#f9efec',
          100: '#f2ddd6',
          200: '#e4beb2',
          300: '#d29784',
          400: '#c26a50',
          500: '#b0432f',
          600: '#9a3a28',
          700: '#7c2f20',
        },
        // 语义状态色：低饱和苔绿 / 赭黄，与暖纸底协调
        moss: {
          50: '#eef3ec',
          100: '#dfe9dd',
          600: '#3a6b4a',
          700: '#2f573c',
        },
        ochre: {
          50: '#f7f1e4',
          100: '#efe3cb',
          600: '#96682a',
          700: '#7a5422',
          800: '#5f421c',
        },
      },
      fontFamily: {
        sans: [
          '"PingFang SC"',
          '"Microsoft YaHei"',
          '"Helvetica Neue"',
          'Helvetica',
          'Arial',
          'sans-serif',
        ],
        // 衬线标题：书卷气来自这里，仅用于页面标题、品牌名与空状态主张
        serif: [
          '"Noto Serif SC"',
          '"Source Han Serif SC"',
          '"Songti SC"',
          'STSong',
          'Georgia',
          'serif',
        ],
        mono: [
          'ui-monospace',
          '"SF Mono"',
          '"Cascadia Mono"',
          '"JetBrains Mono"',
          'Consolas',
          'monospace',
        ],
      },
      keyframes: {
        'fade-in': {
          from: { opacity: '0', transform: 'translateY(4px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: { 'fade-in': 'fade-in 0.2s ease-out' },
    },
  },
  plugins: [],
};
