<template>
  <div class="pub-page">
    <section class="banner">
      <div class="wrap">
        <span class="tag">品牌故事</span>
        <h1 class="b-title">从一线门店出发</h1>
        <p class="b-sub">服装，是顾客生活方式的一部分</p>
      </div>
    </section>

    <section class="wrap body">
      <div class="story">
        <div class="ph ph-gold ph-cover">品牌故事</div>
        <div class="story-text">
          <p class="lead">{{ site.brandStory }}</p>
          <p class="para">多年来，华邦始终扎根零售一线，关注顾客真实的穿着场景与需求变化。我们把对商品的理解、对陈列的打磨、对服务的坚持，沉淀为可持续的品牌力量。</p>
        </div>
      </div>

      <div class="values">
        <div v-for="a in site.advantages" :key="a.title" class="value">
          <span class="v-num">0{{ site.advantages.indexOf(a) + 1 }}</span>
          <div>
            <h3>{{ a.title }}</h3>
            <p>{{ a.desc }}</p>
          </div>
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
.story { display: grid; grid-template-columns: 1fr 1.2fr; gap: 48px; align-items: center; }
.lead { font-size: 18px; color: #0B1F3A; font-weight: 600; line-height: 1.9; }
.para { margin-top: 18px; color: #5b6573; line-height: 2; font-size: 15px; }
.ph { border-radius: 16px; display: flex; align-items: center; justify-content: center; color: rgba(255,255,255,.92); font-weight: 700; font-size: 16px; }
.ph-gold { background: linear-gradient(135deg, #C8A45D, #8B6018); }
.ph-cover { aspect-ratio: 4 / 5; }
.values { margin-top: 60px; display: grid; grid-template-columns: repeat(2, 1fr); gap: 22px; }
.value { display: flex; gap: 16px; padding: 22px; background: #f7f8fa; border-radius: 14px; }
.v-num { font-size: 22px; font-weight: 800; color: #C8A45D; }
.value h3 { color: #0B1F3A; font-size: 16px; font-weight: 700; }
.value p { margin-top: 6px; color: #5b6573; font-size: 13.5px; line-height: 1.7; }
@media (max-width: 760px) { .story { grid-template-columns: 1fr; gap: 24px; } .values { grid-template-columns: 1fr; } }
</style>
