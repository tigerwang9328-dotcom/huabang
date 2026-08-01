<template>
  <div class="pub-page">
    <section class="banner">
      <div class="wrap">
        <span class="tag">公司简介</span>
        <h1 class="b-title">关于华邦服饰</h1>
        <p class="b-sub">{{ site.slogan }}</p>
      </div>
    </section>

    <section class="wrap body">
      <div class="split">
        <div class="text">
          <p class="lead">{{ site.intro }}</p>
          <p class="para">公司以线下门店为主要经营阵地，结合线上渠道，围绕“门店—商品—会员”构建稳定、高效、可复制的零售体系，持续为顾客提供优质的服装产品与购物体验。</p>
        </div>
        <div class="ph ph-tall">公司形象</div>
      </div>

      <div class="facts">
        <div v-for="a in site.advantages" :key="a.title" class="fact">
          <h3>{{ a.title }}</h3>
          <p>{{ a.desc }}</p>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { publicSite } from "@/config/publicSite";
const site = publicSite;
</script>

<style scoped>
.pub-page { color: #1f2937; }
.wrap { width: 100%; max-width: 1100px; margin: 0 auto; padding: 0 24px; }
.banner { background: linear-gradient(135deg, #0B1F3A, #102A4C); color: #fff; padding: 72px 0 60px; }
.tag { display: inline-block; font-size: 12px; letter-spacing: .25em; color: #C8A45D; font-weight: 700; }
.b-title { font-size: clamp(28px, 5vw, 44px); font-weight: 800; margin-top: 14px; }
.b-sub { margin-top: 12px; color: rgba(255,255,255,.65); font-size: 15px; }
.body { padding: 64px 24px 80px; }
.split { display: grid; grid-template-columns: 1.2fr 1fr; gap: 48px; align-items: start; }
.lead { font-size: 18px; color: #0B1F3A; font-weight: 600; line-height: 1.9; }
.para { margin-top: 18px; color: #5b6573; line-height: 2; font-size: 15px; }
.ph { border-radius: 16px; display: flex; align-items: center; justify-content: center; color: rgba(255,255,255,.92); font-weight: 700; font-size: 16px; background: linear-gradient(135deg, #1f3a5f, #2c5580); }
.ph-tall { aspect-ratio: 3 / 4; }
.facts { display: grid; grid-template-columns: repeat(2, 1fr); gap: 20px; margin-top: 56px; }
.fact { padding: 24px; background: #f7f8fa; border-radius: 14px; border-left: 3px solid #C8A45D; }
.fact h3 { color: #0B1F3A; font-size: 16px; font-weight: 700; }
.fact p { margin-top: 8px; color: #5b6573; font-size: 13.5px; line-height: 1.75; }
@media (max-width: 760px) { .split { grid-template-columns: 1fr; gap: 24px; } .facts { grid-template-columns: 1fr; } }
</style>
