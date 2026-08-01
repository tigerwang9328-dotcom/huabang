<template>
  <div class="pub-page">
    <section class="banner">
      <div class="wrap">
        <span class="tag">场地展示</span>
        <h1 class="b-title">公司场地展示</h1>
        <p class="b-sub">现代化的品牌展厅与办公空间</p>
      </div>
    </section>

    <section class="wrap body">
      <div class="grid">
        <article v-for="(sp, i) in site.spaces" :key="sp.title" class="card">
          <div class="ph" :class="i % 2 ? 'ph-gold' : 'ph-navy'">{{ sp.title }}</div>
          <div class="card-body">
            <h3>{{ sp.title }}</h3>
            <p>{{ sp.desc }}</p>
          </div>
        </article>
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
.grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 26px; }
.card { background: #fff; border-radius: 16px; overflow: hidden; box-shadow: 0 6px 22px rgba(15,23,42,.06); transition: transform .18s, box-shadow .18s; }
.card:hover { transform: translateY(-4px); box-shadow: 0 14px 34px rgba(15,23,42,.1); }
.ph { aspect-ratio: 16 / 10; display: flex; align-items: center; justify-content: center; color: rgba(255,255,255,.92); font-weight: 700; font-size: 17px; }
.ph-navy { background: linear-gradient(135deg, #0B1F3A, #1f3a5f); }
.ph-gold { background: linear-gradient(135deg, #C8A45D, #8B6018); }
.card-body { padding: 20px; }
.card-body h3 { font-size: 17px; color: #0B1F3A; font-weight: 700; }
.card-body p { margin-top: 8px; color: #5b6573; font-size: 13.5px; line-height: 1.7; }
@media (max-width: 620px) { .grid { grid-template-columns: 1fr; } }
</style>
