<template>
  <div class="home">
    <!-- ====== 首屏 Hero ====== -->
    <section class="hero">
      <div class="hero-bg" aria-hidden="true"></div>
      <div class="pub-container hero-inner">
        <p class="hero-eyebrow">{{ site.companyEn }}</p>
        <h1 class="hero-title">{{ site.heroTitle }}</h1>
        <p class="hero-sub">{{ site.heroSubtitle }}</p>
        <p class="hero-intro">{{ site.heroIntro }}</p>
        <div class="hero-actions">
          <router-link to="/brand" class="btn btn-primary">了解品牌</router-link>
          <router-link to="/stores" class="btn btn-ghost">查看门店</router-link>
        </div>
      </div>
    </section>

    <!-- ====== 公司简介 ====== -->
    <section class="sec">
      <div class="pub-container sec-split">
        <div class="sec-text">
          <span class="sec-tag">公司简介</span>
          <h2 class="sec-title">以门店为基础，稳健经营</h2>
          <p class="sec-desc">{{ site.intro }}</p>
          <router-link to="/about" class="link-more">了解更多 →</router-link>
        </div>
        <div class="ph ph-wide" data-label="company.jpg">公司形象</div>
      </div>
    </section>

    <!-- ====== 品牌故事 ====== -->
    <section class="sec sec-alt">
      <div class="pub-container sec-split sec-split--reverse">
        <div class="sec-text">
          <span class="sec-tag">品牌故事</span>
          <h2 class="sec-title">服装，是顾客生活方式的一部分</h2>
          <p class="sec-desc">{{ site.brandStory }}</p>
          <router-link to="/brand" class="link-more">品牌故事 →</router-link>
        </div>
        <div class="ph ph-wide ph-gold" data-label="brand.jpg">品牌故事</div>
      </div>
    </section>

    <!-- ====== 产品展示 ====== -->
    <section class="sec">
      <div class="pub-container">
        <div class="sec-head">
          <span class="sec-tag">产品展示</span>
          <h2 class="sec-title">应季上新，贴合生活</h2>
        </div>
        <div class="grid grid-3">
          <article v-for="p in site.products" :key="p.title" class="card">
            <div class="ph ph-card">{{ p.title }}</div>
            <div class="card-body">
              <h3>{{ p.title }}</h3>
              <p>{{ p.desc }}</p>
            </div>
          </article>
        </div>
        <div class="sec-center"><router-link to="/products" class="btn btn-outline">查看全部产品</router-link></div>
      </div>
    </section>

    <!-- ====== 门店形象 ====== -->
    <section class="sec sec-alt">
      <div class="pub-container">
        <div class="sec-head">
          <span class="sec-tag">门店形象</span>
          <h2 class="sec-title">标准化门店，一致的品牌体验</h2>
        </div>
        <div class="grid grid-3">
          <article v-for="s in site.stores" :key="s.title" class="card">
            <div class="ph ph-card ph-navy">{{ s.title }}</div>
            <div class="card-body">
              <h3>{{ s.title }}</h3>
              <p>{{ s.desc }}</p>
            </div>
          </article>
        </div>
        <div class="sec-center"><router-link to="/stores" class="btn btn-outline">查看门店形象</router-link></div>
      </div>
    </section>

    <!-- ====== 场地展示 ====== -->
    <section class="sec">
      <div class="pub-container">
        <div class="sec-head">
          <span class="sec-tag">场地展示</span>
          <h2 class="sec-title">现代化的品牌与办公空间</h2>
        </div>
        <div class="grid grid-2">
          <article v-for="sp in site.spaces" :key="sp.title" class="card">
            <div class="ph ph-card ph-gold">{{ sp.title }}</div>
            <div class="card-body">
              <h3>{{ sp.title }}</h3>
              <p>{{ sp.desc }}</p>
            </div>
          </article>
        </div>
      </div>
    </section>

    <!-- ====== 品牌优势 ====== -->
    <section class="sec sec-dark">
      <div class="pub-container">
        <div class="sec-head sec-head--light">
          <span class="sec-tag sec-tag--light">品牌优势</span>
          <h2 class="sec-title">为什么选择华邦服饰</h2>
        </div>
        <div class="grid grid-4">
          <div v-for="a in site.advantages" :key="a.title" class="adv">
            <div class="adv-num">0{{ site.advantages.indexOf(a) + 1 }}</div>
            <h3>{{ a.title }}</h3>
            <p>{{ a.desc }}</p>
          </div>
        </div>
      </div>
    </section>

    <!-- ====== 联系我们 ====== -->
    <section class="sec sec-cta">
      <div class="pub-container sec-cta-inner">
        <div>
          <h2 class="sec-title">想进一步了解华邦服饰？</h2>
          <p class="sec-desc">欢迎通过以下方式联系我们，获取门店与品牌合作信息。</p>
        </div>
        <router-link to="/contact" class="btn btn-primary btn-lg">联系我们</router-link>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { publicSite } from "@/config/publicSite";
const site = publicSite;
</script>

<style scoped>
.pub-container { width: 100%; max-width: 1200px; margin: 0 auto; padding: 0 24px; }

/* Hero */
.hero { position: relative; min-height: 78vh; display: flex; align-items: center; overflow: hidden; color: #fff; }
.hero-bg {
  position: absolute; inset: 0;
  background:
    radial-gradient(1200px 600px at 75% -10%, rgba(200,164,93,.35), transparent 60%),
    linear-gradient(135deg, #0B1F3A 0%, #102A4C 45%, #071A2F 100%);
}
.hero-bg::after {
  content: ""; position: absolute; inset: 0;
  background-image: linear-gradient(rgba(255,255,255,.04) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,.04) 1px, transparent 1px);
  background-size: 48px 48px; mask-image: radial-gradient(circle at 70% 30%, #000, transparent 70%);
}
.hero-inner { position: relative; padding: 80px 24px; }
.hero-eyebrow { letter-spacing: .35em; font-size: 12px; color: #C8A45D; font-weight: 600; margin-bottom: 18px; }
.hero-title { font-size: clamp(40px, 7vw, 76px); font-weight: 800; letter-spacing: .04em; line-height: 1.05; }
.hero-sub { font-size: clamp(18px, 2.6vw, 26px); margin-top: 18px; color: #eaf0f8; font-weight: 500; }
.hero-intro { font-size: 15px; margin-top: 14px; color: rgba(255,255,255,.65); max-width: 560px; line-height: 1.8; }
.hero-actions { margin-top: 34px; display: flex; gap: 14px; flex-wrap: wrap; }

/* 通用按钮 */
.btn { display: inline-flex; align-items: center; justify-content: center; padding: 12px 26px; border-radius: 28px; font-size: 14.5px; font-weight: 600; text-decoration: none; transition: transform .15s, background .15s, color .15s; }
.btn-lg { padding: 14px 34px; font-size: 15.5px; }
.btn-primary { background: #C8A45D; color: #1a1304; }
.btn-primary:hover { background: #d8b46c; transform: translateY(-2px); }
.btn-ghost { background: rgba(255,255,255,.1); color: #fff; border: 1px solid rgba(255,255,255,.25); }
.btn-ghost:hover { background: rgba(255,255,255,.18); transform: translateY(-2px); }
.btn-outline { background: transparent; color: #0B1F3A; border: 1.5px solid #0B1F3A; }
.btn-outline:hover { background: #0B1F3A; color: #fff; }

/* Section 通用 */
.sec { padding: 76px 0; }
.sec-alt { background: #f7f8fa; }
.sec-head { text-align: center; max-width: 640px; margin: 0 auto 44px; }
.sec-head--light { color: #fff; }
.sec-tag { display: inline-block; font-size: 12px; letter-spacing: .2em; color: #C8A45D; font-weight: 700; margin-bottom: 12px; }
.sec-tag--light { color: #C8A45D; }
.sec-title { font-size: clamp(24px, 3.4vw, 34px); font-weight: 800; color: #0B1F3A; line-height: 1.25; }
.sec-head--light .sec-title { color: #fff; }
.sec-desc { margin-top: 16px; color: #5b6573; line-height: 1.95; font-size: 15px; }
.link-more { display: inline-block; margin-top: 20px; color: #C8A45D; font-weight: 600; text-decoration: none; }
.link-more:hover { color: #a9863f; }
.sec-center { text-align: center; margin-top: 40px; }

/* 两栏 */
.sec-split { display: grid; grid-template-columns: 1fr 1fr; gap: 56px; align-items: center; }
.sec-split--reverse .sec-text { order: 2; }

/* 占位图（无真实图片时的渐变占位，保证不报错） */
.ph {
  border-radius: 16px; display: flex; align-items: center; justify-content: center;
  color: rgba(255,255,255,.92); font-weight: 700; letter-spacing: .05em; font-size: 18px;
  background: linear-gradient(135deg, #1f3a5f, #2c5580); position: relative; overflow: hidden;
}
.ph::after { content: ""; position: absolute; inset: 0; background: radial-gradient(600px 300px at 30% 0%, rgba(255,255,255,.12), transparent 60%); }
.ph-wide { aspect-ratio: 4 / 3; }
.ph-card { aspect-ratio: 4 / 3; font-size: 16px; }
.ph-gold { background: linear-gradient(135deg, #C8A45D, #8B6018); }
.ph-navy { background: linear-gradient(135deg, #0B1F3A, #1f3a5f); }

/* 卡片网格 */
.grid { display: grid; gap: 24px; }
.grid-2 { grid-template-columns: repeat(2, 1fr); }
.grid-3 { grid-template-columns: repeat(3, 1fr); }
.grid-4 { grid-template-columns: repeat(4, 1fr); }
.card { background: #fff; border-radius: 16px; overflow: hidden; box-shadow: 0 6px 22px rgba(15,23,42,.06); transition: transform .18s, box-shadow .18s; }
.card:hover { transform: translateY(-4px); box-shadow: 0 14px 34px rgba(15,23,42,.1); }
.card-body { padding: 20px; }
.card-body h3 { font-size: 17px; color: #0B1F3A; font-weight: 700; }
.card-body p { margin-top: 8px; color: #5b6573; font-size: 13.5px; line-height: 1.7; }

/* 优势区 */
.sec-dark { background: #0B1F3A; }
.adv { padding: 26px; border: 1px solid rgba(255,255,255,.1); border-radius: 16px; background: rgba(255,255,255,.02); }
.adv-num { font-size: 26px; font-weight: 800; color: #C8A45D; }
.adv h3 { margin-top: 12px; color: #fff; font-size: 17px; font-weight: 700; }
.adv p { margin-top: 10px; color: rgba(255,255,255,.6); font-size: 13.5px; line-height: 1.75; }

/* CTA */
.sec-cta { background: #f7f8fa; }
.sec-cta-inner { display: flex; align-items: center; justify-content: space-between; gap: 28px; flex-wrap: wrap; }

/* 响应式 */
@media (max-width: 980px) {
  .grid-4 { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 760px) {
  .sec { padding: 56px 0; }
  .sec-split { grid-template-columns: 1fr; gap: 28px; }
  .sec-split--reverse .sec-text { order: 0; }
  .grid-2, .grid-3, .grid-4 { grid-template-columns: 1fr; }
  .sec-cta-inner { flex-direction: column; align-items: flex-start; }
}
</style>
