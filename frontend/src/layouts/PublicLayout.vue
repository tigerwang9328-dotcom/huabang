<template>
  <div class="pub-layout">
    <!-- ====== 顶部导航 ====== -->
    <header class="pub-header" :class="{ scrolled }">
      <div class="pub-container pub-nav">
        <router-link to="/" class="pub-brand">
          <span class="pub-logo">HB</span>
          <span class="pub-brand-text">
            <span class="pub-brand-cn">{{ site.companyName }}</span>
            <span class="pub-brand-en">{{ site.companyEn }}</span>
          </span>
        </router-link>

        <nav class="pub-menu" :class="{ open: mobileOpen }">
          <router-link
            v-for="item in site.nav"
            :key="item.to"
            :to="item.to"
            class="pub-menu-item"
            @click="mobileOpen = false"
          >{{ item.label }}</router-link>
          <!-- 员工登录小入口（移动端也放进菜单内） -->
          <router-link to="/login" class="pub-staff-btn pub-staff-btn--mobile" @click="mobileOpen = false">
            员工登录
          </router-link>
        </nav>

        <div class="pub-right">
          <router-link to="/login" class="pub-staff-btn">员工登录</router-link>
          <button class="pub-burger" :aria-label="'菜单'" @click="mobileOpen = !mobileOpen">
            <span></span><span></span><span></span>
          </button>
        </div>
      </div>
    </header>

    <!-- ====== 内容 ====== -->
    <main class="pub-main">
      <router-view />
    </main>

    <!-- ====== 页脚 ====== -->
    <footer class="pub-footer">
      <div class="pub-container pub-footer-inner">
        <div class="pub-footer-brand">
          <span class="pub-logo pub-logo--sm">HB</span>
          <div>
            <div class="pub-footer-name">{{ site.companyName }}</div>
            <div class="pub-footer-slogan">{{ site.slogan }}</div>
          </div>
        </div>
        <div class="pub-footer-links">
          <router-link v-for="item in site.nav" :key="item.to" :to="item.to">{{ item.label }}</router-link>
        </div>
        <div class="pub-footer-contact">
          <div>电话：{{ site.contact.phone }}</div>
          <div>邮箱：{{ site.contact.email }}</div>
        </div>
      </div>
      <div class="pub-copyright">© {{ year }} {{ site.companyName }} · 版权所有</div>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from "vue";
import { publicSite } from "@/config/publicSite";

const site = publicSite;
const year = new Date().getFullYear();
const scrolled = ref(false);
const mobileOpen = ref(false);

const onScroll = () => { scrolled.value = window.scrollY > 20; };
onMounted(() => window.addEventListener("scroll", onScroll, { passive: true }));
onUnmounted(() => window.removeEventListener("scroll", onScroll));
</script>

<style scoped>
.pub-layout { min-height: 100vh; display: flex; flex-direction: column; background: #fff; color: #1f2937; }
.pub-container { width: 100%; max-width: 1200px; margin: 0 auto; padding: 0 24px; }

/* 顶部导航 */
.pub-header {
  position: sticky; top: 0; z-index: 100;
  background: rgba(255,255,255,0.92);
  backdrop-filter: saturate(180%) blur(10px);
  border-bottom: 1px solid transparent;
  transition: box-shadow .2s, border-color .2s;
}
.pub-header.scrolled { border-color: #eef0f3; box-shadow: 0 4px 20px rgba(15,23,42,.05); }
.pub-nav { height: 64px; display: flex; align-items: center; justify-content: space-between; gap: 16px; }

.pub-brand { display: flex; align-items: center; gap: 10px; text-decoration: none; }
.pub-logo {
  width: 38px; height: 38px; border-radius: 9px; flex-shrink: 0;
  background: linear-gradient(135deg, #C8A45D, #8B6018);
  color: #fff; font-weight: 800; font-size: 14px;
  display: flex; align-items: center; justify-content: center; letter-spacing: .5px;
}
.pub-logo--sm { width: 34px; height: 34px; }
.pub-brand-text { display: flex; flex-direction: column; line-height: 1.15; }
.pub-brand-cn { font-size: 17px; font-weight: 800; color: #0B1F3A; }
.pub-brand-en { font-size: 10px; letter-spacing: .18em; color: #9aa3b2; }

.pub-menu { display: flex; align-items: center; gap: 28px; }
.pub-menu-item {
  font-size: 14.5px; color: #374151; text-decoration: none; font-weight: 500;
  padding: 6px 0; position: relative; transition: color .15s;
}
.pub-menu-item::after {
  content: ""; position: absolute; left: 0; bottom: 0; height: 2px; width: 0;
  background: #C8A45D; transition: width .2s;
}
.pub-menu-item:hover { color: #0B1F3A; }
.pub-menu-item:hover::after, .pub-menu-item.router-link-exact-active::after { width: 100%; }
.pub-menu-item.router-link-exact-active { color: #0B1F3A; font-weight: 600; }

.pub-right { display: flex; align-items: center; gap: 12px; }
.pub-staff-btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 8px 16px; border-radius: 22px;
  background: #0B1F3A; color: #fff; font-size: 13.5px; font-weight: 600;
  text-decoration: none; transition: background .15s, transform .15s;
  white-space: nowrap;
}
.pub-staff-btn:hover { background: #11304f; transform: translateY(-1px); }
.pub-staff-btn--mobile { display: none; }

.pub-burger { display: none; background: none; border: none; cursor: pointer; flex-direction: column; gap: 4px; padding: 6px; }
.pub-burger span { width: 22px; height: 2px; background: #0B1F3A; border-radius: 2px; display: block; }

.pub-main { flex: 1; }

/* 页脚 */
.pub-footer { background: #0B1F3A; color: rgba(255,255,255,.75); margin-top: 40px; }
.pub-footer-inner { display: flex; flex-wrap: wrap; gap: 32px; justify-content: space-between; padding-top: 48px; padding-bottom: 28px; }
.pub-footer-brand { display: flex; align-items: center; gap: 12px; }
.pub-footer-name { font-size: 16px; font-weight: 700; color: #fff; }
.pub-footer-slogan { font-size: 12.5px; color: rgba(255,255,255,.5); margin-top: 4px; }
.pub-footer-links { display: flex; flex-wrap: wrap; gap: 18px; align-content: flex-start; }
.pub-footer-links a { color: rgba(255,255,255,.7); text-decoration: none; font-size: 13.5px; }
.pub-footer-links a:hover { color: #C8A45D; }
.pub-footer-contact { font-size: 13px; line-height: 1.9; color: rgba(255,255,255,.6); }
.pub-copyright { border-top: 1px solid rgba(255,255,255,.08); text-align: center; padding: 16px; font-size: 12px; color: rgba(255,255,255,.4); }

/* 响应式 */
@media (max-width: 860px) {
  .pub-menu {
    position: absolute; top: 64px; left: 0; right: 0;
    flex-direction: column; align-items: stretch; gap: 0;
    background: #fff; border-bottom: 1px solid #eef0f3;
    padding: 8px 24px 16px; box-shadow: 0 12px 24px rgba(15,23,42,.08);
    display: none;
  }
  .pub-menu.open { display: flex; }
  .pub-menu-item { padding: 12px 0; border-bottom: 1px solid #f3f4f6; }
  .pub-menu-item::after { display: none; }
  .pub-staff-btn:not(.pub-staff-btn--mobile) { display: none; }
  .pub-staff-btn--mobile { display: inline-flex; justify-content: center; margin-top: 12px; }
  .pub-burger { display: flex; }
}
</style>
