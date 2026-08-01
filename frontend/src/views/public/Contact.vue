<template>
  <div class="pub-page">
    <section class="banner">
      <div class="wrap">
        <span class="tag">联系我们</span>
        <h1 class="b-title">联系华邦服饰</h1>
        <p class="b-sub">欢迎了解门店、品牌与合作信息</p>
      </div>
    </section>

    <section class="wrap body">
      <div class="grid">
        <div class="info">
          <div class="row"><span class="k">公司名称</span><span class="v">{{ c.company }}</span></div>
          <div class="row"><span class="k">联系电话</span><span class="v">{{ c.phone }}</span></div>
          <div class="row"><span class="k">电子邮箱</span><span class="v">{{ c.email }}</span></div>
          <div class="row"><span class="k">公司地址</span><span class="v">{{ c.address }}</span></div>
          <div class="row"><span class="k">营业时间</span><span class="v">{{ c.hours }}</span></div>
        </div>
        <div class="ph">联系我们</div>
      </div>
      <p class="note">如需员工内部系统登录，请点击右上角“员工登录”。</p>
    </section>
  </div>
</template>

<script setup lang="ts">
import { publicSite } from "@/config/publicSite";
const c = publicSite.contact;
</script>

<style scoped>
.pub-page { color: #1f2937; }
.wrap { width: 100%; max-width: 1100px; margin: 0 auto; padding: 0 24px; }
.banner { background: linear-gradient(135deg, #0B1F3A, #102A4C); color: #fff; padding: 72px 0 60px; }
.tag { display: inline-block; font-size: 12px; letter-spacing: .25em; color: #C8A45D; font-weight: 700; }
.b-title { font-size: clamp(28px, 5vw, 44px); font-weight: 800; margin-top: 14px; }
.b-sub { margin-top: 12px; color: rgba(255,255,255,.65); font-size: 15px; }
.body { padding: 64px 24px 80px; }
.grid { display: grid; grid-template-columns: 1.1fr 1fr; gap: 48px; align-items: stretch; }
.info { display: flex; flex-direction: column; gap: 4px; }
.row { display: flex; gap: 18px; padding: 18px 4px; border-bottom: 1px solid #eef0f3; }
.k { width: 84px; flex-shrink: 0; color: #9aa3b2; font-size: 13.5px; }
.v { color: #0B1F3A; font-size: 15px; font-weight: 600; }
.ph { border-radius: 16px; min-height: 280px; display: flex; align-items: center; justify-content: center; color: rgba(255,255,255,.92); font-weight: 700; font-size: 17px; background: linear-gradient(135deg, #1f3a5f, #2c5580); }
.note { margin-top: 36px; text-align: center; color: #9aa3b2; font-size: 13px; }
@media (max-width: 760px) { .grid { grid-template-columns: 1fr; gap: 24px; } }
</style>
