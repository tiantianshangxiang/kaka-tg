import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import federation from '@originjs/vite-plugin-federation'

// Module Federation：把 Config / Page 两个 Vue 组件暴露给 MoviePilot 前端远程加载。
// 产物 dist/remoteEntry.js 由 MP 前端动态导入，配置弹窗渲染 Config，详情页渲染 Page。
export default defineConfig({
  plugins: [
    vue(),
    federation({
      name: 'TgSearch115',
      filename: 'remoteEntry.js',
      exposes: {
        './Config': './src/components/Config.vue',
        './Page': './src/components/Page.vue',
      },
      shared: {
        vue: { requiredVersion: false, generate: false },
      },
      format: 'esm',
    }),
  ],
  build: {
    target: 'esnext',
    minify: false,
    cssCodeSplit: true,
    emptyOutDir: true, // 构建前清空 dist，避免旧 hash 产物残留成孤儿文件
  },
  css: {
    postcss: {
      plugins: [
        // 去掉 @charset，避免联邦产物里出现非法字符
        {
          postcssPlugin: 'internal:charset-removal',
          AtRule: {
            charset: (atRule) => {
              if (atRule.name === 'charset') atRule.remove()
            },
          },
        },
        // 关键：剥掉 .v-* / .mdi-* 规则。MoviePilot 主应用已全局加载 Vuetify，
        // 插件只保留自身自定义样式，避免与主应用 Vuetify 样式重复/冲突。
        {
          postcssPlugin: 'vuetify-filter',
          Root(root) {
            root.walkRules((rule) => {
              if (rule.selector && (rule.selector.includes('.v-') || rule.selector.includes('.mdi-'))) {
                rule.remove()
              }
            })
          },
        },
      ],
    },
  },
})
