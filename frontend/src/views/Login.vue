<template>
  <div class="lp-root">
    <!-- ══ 动态背景层 ══ -->
    <div class="lp-bg" aria-hidden="true">
      <div class="bg-orb bg-orb-1"></div>
      <div class="bg-orb bg-orb-2"></div>
      <div class="bg-orb bg-orb-3"></div>
      <div class="bg-grid"></div>
      <div class="bg-streams">
        <div class="sl sl-1"></div>
        <div class="sl sl-2"></div>
        <div class="sl sl-3"></div>
        <div class="sl sl-4"></div>
        <div class="sl sl-5"></div>
        <div class="sl sl-6"></div>
      </div>
    </div>

    <div class="lp-container">
      <!-- ══ 左侧品牌区 ══ -->
      <aside class="lp-brand" :class="{ 'lp-in': ready }">

        <!-- Logo 区 -->
        <div class="b-logo">
          <div class="b-gem">
            <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
              <polygon points="24,3 43,14 43,34 24,45 5,34 5,14"
                fill="url(#g1)" stroke="rgba(212,168,83,0.5)" stroke-width="1.2"/>
              <text x="24" y="28" text-anchor="middle" fill="white"
                font-size="12" font-weight="800"
                font-family="-apple-system,BlinkMacSystemFont,'PingFang SC',sans-serif">HB</text>
              <defs>
                <linearGradient id="g1" x1="0%" y1="0%" x2="100%" y2="100%">
                  <stop offset="0%" stop-color="#D4A853"/>
                  <stop offset="48%" stop-color="#F2D072"/>
                  <stop offset="100%" stop-color="#8B6018"/>
                </linearGradient>
              </defs>
            </svg>
          </div>
          <div class="b-names">
            <div class="b-cn">华邦集团 <span class="b-sep">·</span> AI智能分析系统</div>
            <div class="b-en">HB-AI Hub &nbsp;·&nbsp; Enterprise Intelligence Platform</div>
          </div>
        </div>

        <!-- 主标题 -->
        <div class="b-hl">
          <h1 class="hl-white">数据织造未来</h1>
          <h1 class="hl-gold">智能驱动决策</h1>
        </div>

        <!-- 副文案 -->
        <p class="b-desc">
          华邦AI中台无缝连接百世ERP、金蝶财务、供应链、人力资源及全渠道会员数据。
          以新一代AI算法深度剖析采购、库存、商品、销售与资金流向，为集团提供
          全时段、全视角的经营大局观，助力精准商业决策。
        </p>

        <!-- 数据汇聚可视化 -->
        <div class="conv">
          <div class="conv-srcs">
            <div
              v-for="(s, i) in sources"
              :key="s.name"
              class="conv-src"
              :style="{ animationDelay: (i * 0.13) + 's' }"
            >
              <span class="src-dot" :style="{ background: s.color, boxShadow: '0 0 7px ' + s.color }"></span>
              <span class="src-name">{{ s.name }}</span>
            </div>
          </div>

          <div class="conv-mid">
            <div class="flow-bar">
              <div class="flow-shine"></div>
            </div>
            <svg viewBox="0 0 24 24" fill="none" width="22" height="22" class="flow-arr">
              <path d="M5 12h14M13 6l6 6-6 6" stroke="url(#arr)" stroke-width="2"
                stroke-linecap="round" stroke-linejoin="round"/>
              <defs>
                <linearGradient id="arr" x1="0" y1="0" x2="1" y2="0">
                  <stop offset="0%" stop-color="#3B82F6"/>
                  <stop offset="100%" stop-color="#D4A853"/>
                </linearGradient>
              </defs>
            </svg>
          </div>

          <div class="conv-hub">
            <div class="hub-core">AI</div>
            <div class="hub-r hub-r1"></div>
            <div class="hub-r hub-r2"></div>
          </div>
        </div>

        <div class="b-tag">FASHION · DATA · INTELLIGENCE</div>
      </aside>

      <!-- ══ 右侧登录区 ══ -->
      <section class="lp-right" :class="{ 'lp-in': ready }">
        <div class="glass-card">
          <div class="card-top-line"></div>

          <!-- 卡头 -->
          <div class="card-head">
            <div class="c-gem">
              <svg width="40" height="40" viewBox="0 0 48 48" fill="none">
                <polygon points="24,3 43,14 43,34 24,45 5,34 5,14"
                  fill="url(#g2)" stroke="rgba(212,168,83,0.4)" stroke-width="1.2"/>
                <text x="24" y="28" text-anchor="middle" fill="white"
                  font-size="12" font-weight="800"
                  font-family="-apple-system,BlinkMacSystemFont,'PingFang SC',sans-serif">HB</text>
                <defs>
                  <linearGradient id="g2" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stop-color="#D4A853"/>
                    <stop offset="48%" stop-color="#F2D072"/>
                    <stop offset="100%" stop-color="#8B6018"/>
                  </linearGradient>
                </defs>
              </svg>
            </div>
            <h2 class="c-title">欢迎登录</h2>
            <p class="c-sub">华邦集团 · AI智能分析系统</p>
          </div>

          <!-- 登录表单 -->
          <form @submit.prevent="handleLogin" novalidate>

            <!-- 用户名 -->
            <div class="hb-field" :class="{ foc: af === 'u', has: !!form.username }">
              <label class="f-label">用户名 / 手机号</label>
              <div class="f-inner">
                <svg class="f-ico" viewBox="0 0 20 20" fill="none">
                  <circle cx="10" cy="7" r="3" stroke="currentColor" stroke-width="1.4"/>
                  <path d="M3.5 17c0-3.86 2.91-7 6.5-7s6.5 3.14 6.5 7"
                    stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>
                </svg>
                <input
                  v-model="form.username"
                  type="text"
                  placeholder="请输入用户名或手机号"
                  @focus="af = 'u'"
                  @blur="af = ''"
                  autocomplete="username"
                />
              </div>
            </div>

            <!-- 密码 -->
            <div class="hb-field" :class="{ foc: af === 'p', has: !!form.password }">
              <label class="f-label">密 码</label>
              <div class="f-inner">
                <svg class="f-ico" viewBox="0 0 20 20" fill="none">
                  <rect x="4" y="9" width="12" height="9" rx="2"
                    stroke="currentColor" stroke-width="1.4"/>
                  <path d="M7 9V7a3 3 0 016 0v2"
                    stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>
                  <circle cx="10" cy="13.5" r="1.2" fill="currentColor" opacity="0.5"/>
                </svg>
                <input
                  v-model="form.password"
                  :type="showPwd ? 'text' : 'password'"
                  placeholder="请输入密码"
                  @focus="af = 'p'"
                  @blur="af = ''"
                  autocomplete="current-password"
                />
                <button type="button" class="eye-btn" @click="showPwd = !showPwd" tabindex="-1">
                  <svg v-if="!showPwd" viewBox="0 0 20 20" fill="none">
                    <path d="M2 10s3.2-6 8-6 8 6 8 6-3.2 6-8 6-8-6-8-6z"
                      stroke="currentColor" stroke-width="1.4"/>
                    <circle cx="10" cy="10" r="2.5" stroke="currentColor" stroke-width="1.4"/>
                  </svg>
                  <svg v-else viewBox="0 0 20 20" fill="none">
                    <path d="M3 3l14 14M10 4C5 4 2 10 2 10s.7 1.6 2.2 3.3M17.8 6.7C19.3 8.4 18 10 18 10s-3.2 6-8 6c-1.4 0-2.7-.4-3.9-1"
                      stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>
                    <path d="M7.6 7.6A2.5 2.5 0 0112.4 12.4"
                      stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>
                  </svg>
                </button>
              </div>
            </div>

            <!-- 记住 / 忘记 -->
            <div class="form-opts">
              <label class="hb-chk">
                <input type="checkbox" v-model="rememberMe"/>
                <span class="chk-box"></span>
                <span>记住用户名</span>
              </label>
              <a href="#" class="forgot" @click.prevent>忘记密码？</a>
            </div>

            <!-- 登录按钮 -->
            <button type="submit" class="sub-btn" :disabled="loading">
              <span class="btn-shine"></span>
              <span class="btn-txt">
                <svg v-if="loading" class="spinner" viewBox="0 0 24 24" fill="none">
                  <circle cx="12" cy="12" r="10" stroke="rgba(255,255,255,0.25)" stroke-width="3"/>
                  <path d="M12 2a10 10 0 0110 10" stroke="white" stroke-width="3" stroke-linecap="round"/>
                </svg>
                {{ loading ? "登录中..." : "登 录" }}
              </span>
            </button>

            <div class="register-entry">
              <span>还没有中台账号？</span>
              <button type="button" @click="openRegisterDialog">注册申请</button>
            </div>

          </form>

          <el-dialog
            v-model="registerVisible"
            title="华邦AI中台 · 注册申请"
            width="620px"
            class="register-dialog"
            append-to-body
          >
            <div class="register-intro">
              <strong>企业账号申请</strong>
              <p>请填写真实信息。提交后账号不会立即启用，需系统管理员审核岗位、门店与权限范围后开通。</p>
            </div>
            <el-form :model="registerForm" label-width="96px" class="register-form">
              <div class="form-section-title">账号信息</div>
              <el-form-item label="用户名" required>
                <el-input v-model="registerForm.username" placeholder="建议使用姓名拼音 / 工号 / 手机号" autocomplete="off" />
              </el-form-item>
              <div class="register-two-col">
                <el-form-item label="登录密码" required>
                  <el-input v-model="registerForm.password" type="password" show-password placeholder="至少8位" autocomplete="new-password" />
                </el-form-item>
                <el-form-item label="确认密码" required>
                  <el-input v-model="registerForm.confirm_password" type="password" show-password placeholder="再次输入密码" autocomplete="new-password" />
                </el-form-item>
              </div>

              <div class="form-section-title">身份信息</div>
              <div class="register-two-col">
                <el-form-item label="真实姓名" required>
                  <el-input v-model="registerForm.real_name" placeholder="请输入真实姓名" />
                </el-form-item>
                <el-form-item label="手机号" required>
                  <el-input v-model="registerForm.phone" placeholder="用于管理员核验身份" />
                </el-form-item>
              </div>
              <el-form-item label="部门/门店">
                <el-input v-model="registerForm.department" placeholder="如：运营部 / 商品部 / 成都某门店" />
              </el-form-item>

              <div class="form-section-title">权限申请</div>
              <div class="register-two-col">
                <el-form-item label="申请岗位" required>
                  <el-select v-model="registerForm.apply_role" placeholder="请选择岗位" style="width: 100%">
                    <el-option v-for="role in registerRoles" :key="role.value" :label="role.label" :value="role.value" />
                  </el-select>
                </el-form-item>
                <el-form-item label="门店编码">
                  <el-input v-model="registerForm.store_code" placeholder="店长/导购必填" />
                </el-form-item>
              </div>
              <el-form-item label="申请说明">
                <el-input v-model="registerForm.remark" type="textarea" :rows="3" placeholder="请说明申请原因、所属业务范围或需要查看的数据模块" />
              </el-form-item>
            </el-form>
            <template #footer>
              <el-button @click="registerVisible = false">取消</el-button>
              <el-button type="primary" :loading="registerSubmitting" @click="submitRegisterApply">提交申请</el-button>
            </template>
          </el-dialog>

          <!-- 版权 -->
          <div class="card-ft">
            © 2026 华邦集团 版权所有 &nbsp;|&nbsp; 华邦AI中台技术支持
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { authApi } from "@/api/auth";
import { ElMessage } from "element-plus";

const router    = useRouter();
const authStore = useAuthStore();

const form       = reactive({ username: "", password: "" });
const loading    = ref(false);
const showPwd    = ref(false);
const rememberMe = ref(false);
const af         = ref("");   // active field
const ready      = ref(false);
const registerVisible = ref(false);
const registerSubmitting = ref(false);
const registerForm = reactive({
  username: "",
  password: "",
  confirm_password: "",
  real_name: "",
  phone: "",
  apply_role: "",
  department: "",
  store_code: "",
  remark: "",
});
const registerRoles = [
  { label: "BOSS", value: "boss" },
  { label: "总经理", value: "ceo" },
  { label: "商品经理", value: "product_manager" },
  { label: "商品专员", value: "product_specialist" },
  { label: "财务经理", value: "finance_manager" },
  { label: "会计", value: "accountant" },
  { label: "出纳", value: "cashier" },
  { label: "仓库主管", value: "warehouse_manager" },
  { label: "运营经理", value: "operation_manager" },
  { label: "店长", value: "store_manager" },
  { label: "导购", value: "guide" },
];
const REMEMBER_KEY = "hb_login_remember";
const LEGACY_REMEMBER_KEYS = ["hb_login_remember", "hb_remember_password", "remember_password"];

const sources = [
  { name: "百世ERP",   color: "#3B82F6" },
  { name: "金蝶财务",  color: "#8B5CF6" },
  { name: "供应链管理", color: "#10B981" },
  { name: "全渠道销售", color: "#F59E0B" },
  { name: "会员系统",  color: "#EC4899" },
  { name: "人力资源",  color: "#06B6D4" },
];

function loadRememberedLogin() {
  try {
    for (const key of LEGACY_REMEMBER_KEYS) {
      const raw = localStorage.getItem(key);
      if (!raw) continue;
      const saved = JSON.parse(raw);
      if (saved?.password) {
        delete saved.password;
        localStorage.setItem(REMEMBER_KEY, JSON.stringify({ username: saved.username || "" }));
      }
    }
    const raw = localStorage.getItem(REMEMBER_KEY);
    if (!raw) return;
    const saved = JSON.parse(raw);
    if (saved?.username) {
      form.username = saved.username;
      form.password = "";
      rememberMe.value = true;
    }
  } catch {
    localStorage.removeItem(REMEMBER_KEY);
  }
}

function saveRememberedLogin() {
  if (!rememberMe.value) {
    localStorage.removeItem(REMEMBER_KEY);
    return;
  }
  localStorage.setItem(REMEMBER_KEY, JSON.stringify({ username: form.username.trim() }));
}

onMounted(() => {
  loadRememberedLogin();
  setTimeout(() => { ready.value = true; }, 60);
});



const openRegisterDialog = () => {
  registerVisible.value = true;
};

const resetRegisterForm = () => {
  registerForm.username = "";
  registerForm.password = "";
  registerForm.confirm_password = "";
  registerForm.real_name = "";
  registerForm.phone = "";
  registerForm.apply_role = "";
  registerForm.department = "";
  registerForm.store_code = "";
  registerForm.remark = "";
};

const submitRegisterApply = async () => {
  if (!registerForm.username.trim() || !registerForm.password || !registerForm.confirm_password) {
    ElMessage({ message: "请填写用户名、密码和确认密码", type: "warning", duration: 2600 });
    return;
  }
  if (registerForm.password.length < 8) {
    ElMessage({ message: "密码至少8位", type: "warning", duration: 2600 });
    return;
  }
  if (registerForm.password !== registerForm.confirm_password) {
    ElMessage({ message: "两次输入的密码不一致", type: "warning", duration: 2600 });
    return;
  }
  if (!registerForm.real_name.trim() || !registerForm.phone.trim() || !registerForm.apply_role) {
    ElMessage({ message: "请填写姓名、手机号并选择申请岗位", type: "warning", duration: 2600 });
    return;
  }
  if (["store_manager", "guide"].includes(registerForm.apply_role) && !registerForm.store_code.trim()) {
    ElMessage({ message: "店长/导购申请必须填写门店编码", type: "warning", duration: 2600 });
    return;
  }
  registerSubmitting.value = true;
  try {
    await authApi.registerApply({
      username: registerForm.username.trim(),
      password: registerForm.password,
      confirm_password: registerForm.confirm_password,
      real_name: registerForm.real_name.trim(),
      phone: registerForm.phone.trim(),
      apply_role: registerForm.apply_role,
      department: registerForm.department.trim(),
      store_code: registerForm.store_code.trim(),
      remark: registerForm.remark.trim(),
    });
    ElMessage({ message: "注册申请已提交，请等待管理员审核", type: "success", duration: 3200 });
    registerVisible.value = false;
    resetRegisterForm();
  } catch (e: any) {
    ElMessage({ message: e.message || "提交失败，请稍后重试", type: "error", duration: 3000 });
  } finally {
    registerSubmitting.value = false;
  }
};

const getPermissionHomePath = () => {
  const candidates: Array<[string, string]> = [
    ["/app/dashboard", "dashboard:overview:view"],
    ["/app/ai-diagnosis", "diagnosis:overall:view"],
    ["/app/store", "sales:store:view"],
    ["/app/product", "product:overview:view"],
    ["/app/inventory", "inventory:overview:view"],
    ["/app/fin/overview", "finance:overview:view"],
    ["/app/hr/overview", "hr:overview:view"],
    ["/app/ai", "knowledge:ai:view"],
    ["/app/system/admin", "system:dashboard:view"],
  ];
  return candidates.find(([, permission]) => authStore.hasPermission(permission))?.[0] || "/app/ai";
};

const handleLogin = async () => {
  const username = form.username.trim();
  if (!username || !form.password) {
    ElMessage({ message: "请填写用户名和密码", type: "warning", duration: 2500 });
    return;
  }
  loading.value = true;
  try {
    form.username = username;
    await authStore.login(username, form.password);
    saveRememberedLogin();
    ElMessage({ message: "登录成功，欢迎回来", type: "success", duration: 2000 });
    router.push(getPermissionHomePath());
  } catch (e: any) {
    ElMessage({
      message: e.message || "用户名或密码错误，请重试",
      type: "error",
      duration: 3000,
    });
  } finally {
    loading.value = false;
  }
};
</script>

<style scoped>
/* ════════════════════════════════════
   PAGE ROOT
════════════════════════════════════ */
.lp-root {
  min-height: 100vh;
  width: 100%;
  background: #050510;
  overflow: hidden;
  position: relative;
  display: flex;
}

/* ════════════════════════════════════
   ANIMATED BACKGROUND
════════════════════════════════════ */
.lp-bg {
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  overflow: hidden;
}

.bg-orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(90px);
}
.bg-orb-1 {
  width: 760px; height: 760px;
  background: radial-gradient(circle, rgba(37,99,235,0.22) 0%, transparent 70%);
  top: -240px; left: -190px;
  animation: orbDrift 22s ease-in-out infinite alternate;
}
.bg-orb-2 {
  width: 620px; height: 620px;
  background: radial-gradient(circle, rgba(124,58,237,0.17) 0%, transparent 70%);
  bottom: -140px; right: -130px;
  animation: orbDrift 28s ease-in-out infinite alternate-reverse;
}
.bg-orb-3 {
  width: 400px; height: 400px;
  background: radial-gradient(circle, rgba(212,168,83,0.09) 0%, transparent 70%);
  top: 35%; left: 43%;
  animation: orbDrift 19s ease-in-out infinite alternate;
}
@keyframes orbDrift {
  0%   { transform: translate(0, 0) scale(1); }
  50%  { transform: translate(30px, -24px) scale(1.07); }
  100% { transform: translate(-22px, 28px) scale(0.93); }
}

.bg-grid {
  position: absolute;
  inset: 0;
  background-image: radial-gradient(circle, rgba(255,255,255,0.036) 1px, transparent 1px);
  background-size: 36px 36px;
}

/* Data stream lines */
.bg-streams { position: absolute; inset: 0; }
.sl {
  position: absolute;
  height: 1px;
  width: 55%;
  left: -60%;
  background: linear-gradient(
    90deg,
    transparent 0%,
    rgba(59,130,246,0.3) 40%,
    rgba(212,168,83,0.4) 65%,
    transparent 100%
  );
  animation: streamFlow linear infinite;
}
.sl-1 { top: 11%; animation-duration: 10s;  animation-delay: 0s;   }
.sl-2 { top: 25%; animation-duration: 13s;  animation-delay: 2.3s; opacity: 0.65; }
.sl-3 { top: 40%; animation-duration: 8.5s; animation-delay: 4.6s; width: 42%; }
.sl-4 { top: 56%; animation-duration: 14s;  animation-delay: 1.2s; opacity: 0.5; }
.sl-5 { top: 71%; animation-duration: 11s;  animation-delay: 3.4s; width: 48%; }
.sl-6 { top: 87%; animation-duration: 9s;   animation-delay: 6.1s; opacity: 0.55; }
@keyframes streamFlow {
  0%   { transform: translateX(0);           opacity: 0; }
  8%   {                                     opacity: 1; }
  92%  {                                     opacity: 1; }
  100% { transform: translateX(calc(100vw + 65%)); opacity: 0; }
}

/* ════════════════════════════════════
   MAIN CONTAINER
════════════════════════════════════ */
.lp-container {
  position: relative;
  z-index: 1;
  display: flex;
  width: 100%;
  min-height: 100vh;
}

/* ════════════════════════════════════
   BRAND SIDE
════════════════════════════════════ */
.lp-brand {
  flex: 0 0 57%;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 60px 68px 60px 84px;
  opacity: 0;
  transform: translateY(28px);
  transition: opacity 0.78s ease, transform 0.78s ease;
}
.lp-brand.lp-in { opacity: 1; transform: translateY(0); }

/* Logo */
.b-logo {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 54px;
}
.b-gem {
  flex-shrink: 0;
  filter: drop-shadow(0 0 15px rgba(212,168,83,0.5));
}
.b-names  { display: flex; flex-direction: column; gap: 5px; }
.b-cn {
  font-size: 17px;
  font-weight: 700;
  color: rgba(255,255,255,0.92);
  letter-spacing: 0.025em;
}
.b-sep { color: #D4A853; margin: 0 5px; }
.b-en {
  font-size: 10.5px;
  color: rgba(255,255,255,0.24);
  letter-spacing: 0.1em;
}

/* Headline */
.b-hl { margin-bottom: 26px; }
.b-hl h1 {
  font-size: clamp(36px, 3.7vw, 56px);
  font-weight: 800;
  line-height: 1.28;
  margin: 0;
  letter-spacing: -0.015em;
}
.hl-white { color: #ffffff; }
.hl-gold {
  background: linear-gradient(115deg, #D4A853 0%, #F2D072 48%, #C08820 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

/* Desc */
.b-desc {
  font-size: 14px;
  line-height: 1.9;
  color: rgba(255,255,255,0.38);
  max-width: 520px;
  margin: 0 0 44px;
}

/* ── Convergence visual ── */
.conv {
  display: flex;
  align-items: center;
  gap: 20px;
  margin-bottom: 40px;
  flex-wrap: wrap;
}
.conv-srcs {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px 24px;
}
.conv-src {
  display: flex;
  align-items: center;
  gap: 9px;
  animation: srcIn 0.5s ease both;
}
@keyframes srcIn {
  from { opacity: 0; transform: translateX(-10px); }
  to   { opacity: 1; transform: translateX(0); }
}
.src-dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.src-name {
  font-size: 12.5px;
  color: rgba(255,255,255,0.5);
  white-space: nowrap;
}

.conv-mid {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}
.flow-bar {
  width: 58px; height: 1px;
  background: linear-gradient(90deg, rgba(59,130,246,0.7), rgba(212,168,83,0.85));
  position: relative;
  overflow: hidden;
}
.flow-shine {
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, transparent, rgba(255,255,255,0.9), transparent);
  animation: shineBar 2.2s linear infinite;
}
@keyframes shineBar {
  0%   { transform: translateX(-100%); }
  100% { transform: translateX(100%); }
}
.flow-arr { flex-shrink: 0; }

.conv-hub {
  position: relative;
  width: 62px; height: 62px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.hub-core {
  position: relative;
  z-index: 1;
  width: 44px; height: 44px;
  background: linear-gradient(135deg, #1D4ED8, #7C3AED);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 800;
  color: white;
  letter-spacing: 0.05em;
  box-shadow: 0 0 26px rgba(29,78,216,0.6), 0 0 52px rgba(124,58,237,0.28);
}
.hub-r {
  position: absolute;
  border-radius: 50%;
  border: 1px solid rgba(29,78,216,0.38);
  animation: rPulse 2.8s ease-in-out infinite;
}
.hub-r1 { inset: -9px; }
.hub-r2 { inset: -19px; border-color: rgba(29,78,216,0.16); animation-delay: 1.4s; }
@keyframes rPulse {
  0%,100% { transform: scale(1);    opacity: 0.7; }
  50%     { transform: scale(1.08); opacity: 0.28; }
}

.b-tag {
  font-size: 10.5px;
  letter-spacing: 0.28em;
  color: rgba(255,255,255,0.15);
  font-weight: 500;
}

/* ════════════════════════════════════
   LOGIN SIDE
════════════════════════════════════ */
.lp-right {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 48px 52px 48px 20px;
  opacity: 0;
  transform: translateY(28px);
  transition: opacity 0.78s ease 0.2s, transform 0.78s ease 0.2s;
}
.lp-right.lp-in { opacity: 1; transform: translateY(0); }

/* Glass card */
.glass-card {
  width: 100%;
  max-width: 424px;
  background: rgba(255,255,255,0.038);
  backdrop-filter: blur(30px) saturate(1.7);
  -webkit-backdrop-filter: blur(30px) saturate(1.7);
  border: 1px solid rgba(255,255,255,0.09);
  border-radius: 22px;
  padding: 50px 48px 38px;
  position: relative;
  overflow: hidden;
  box-shadow:
    0 0 0 1px rgba(255,255,255,0.022),
    0 44px 96px rgba(0,0,0,0.58),
    inset 0 1px 0 rgba(255,255,255,0.09);
}

/* Top accent line */
.card-top-line {
  position: absolute;
  top: -1px; left: 50%;
  transform: translateX(-50%);
  width: 68%;
  height: 1px;
  background: linear-gradient(
    90deg,
    transparent,
    rgba(79,110,247,0.9),
    rgba(212,168,83,0.7),
    transparent
  );
}

/* Card header */
.card-head { text-align: center; margin-bottom: 40px; }
.c-gem {
  display: inline-flex;
  margin-bottom: 18px;
  filter: drop-shadow(0 0 12px rgba(212,168,83,0.45));
}
.c-title {
  font-size: 25px;
  font-weight: 700;
  color: rgba(255,255,255,0.92);
  margin: 0 0 8px;
  letter-spacing: -0.01em;
}
.c-sub {
  font-size: 13px;
  color: rgba(255,255,255,0.27);
  margin: 0;
}

/* ── Input fields ── */
.hb-field { margin-bottom: 22px; }

.f-label {
  display: block;
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgba(255,255,255,0.3);
  margin-bottom: 10px;
  transition: color 0.22s;
}
.hb-field.foc .f-label { color: rgba(99,130,247,0.9); }

.f-inner {
  display: flex;
  align-items: center;
  gap: 11px;
  height: 52px;
  padding: 0 15px;
  background: rgba(255,255,255,0.046);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 11px;
  transition: background 0.22s, border-color 0.22s, box-shadow 0.22s;
}
.hb-field.foc .f-inner {
  background: rgba(79,110,247,0.07);
  border-color: rgba(79,110,247,0.45);
  box-shadow: 0 0 0 3px rgba(79,110,247,0.1);
}

.f-ico {
  width: 16px; height: 16px;
  flex-shrink: 0;
  color: rgba(255,255,255,0.22);
  transition: color 0.22s;
}
.hb-field.foc .f-ico { color: rgba(99,130,247,0.72); }

.f-inner input {
  flex: 1;
  background: none;
  border: none;
  outline: none;
  font-size: 14px;
  color: rgba(255,255,255,0.88);
  font-family: inherit;
  min-width: 0;
}
.f-inner input::placeholder { color: rgba(255,255,255,0.18); }

.eye-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: 3px;
  color: rgba(255,255,255,0.22);
  display: flex;
  align-items: center;
  flex-shrink: 0;
  transition: color 0.2s;
  border-radius: 4px;
}
.eye-btn:hover { color: rgba(255,255,255,0.58); }
.eye-btn svg  { width: 16px; height: 16px; }

/* ── Options row ── */
.form-opts {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 28px;
}
.hb-chk {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  font-size: 13px;
  color: rgba(255,255,255,0.4);
  user-select: none;
}
.hb-chk input[type="checkbox"] { display: none; }
.chk-box {
  width: 16px; height: 16px;
  border: 1.5px solid rgba(255,255,255,0.2);
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  font-size: 10px;
  color: white;
  transition: all 0.2s;
}
.hb-chk input[type="checkbox"]:checked + .chk-box {
  background: #4F6EF7;
  border-color: #4F6EF7;
}
.hb-chk input[type="checkbox"]:checked + .chk-box::after {
  content: "✓";
  font-weight: 700;
  line-height: 1;
}
.forgot {
  font-size: 13px;
  color: rgba(99,130,247,0.65);
  text-decoration: none;
  transition: color 0.2s;
}
.forgot:hover { color: rgba(212,168,83,0.85); }

/* ── Submit button ── */
.sub-btn {
  width: 100%;
  height: 52px;
  background: linear-gradient(120deg, #1D4ED8 0%, #4F6EF7 50%, #7C3AED 100%);
  background-size: 200% 100%;
  background-position: 0% 50%;
  border: none;
  border-radius: 11px;
  color: white;
  font-size: 15.5px;
  font-weight: 700;
  letter-spacing: 0.1em;
  cursor: pointer;
  position: relative;
  overflow: hidden;
  transition:
    background-position 0.55s ease,
    box-shadow 0.3s ease,
    transform 0.15s ease,
    opacity 0.2s;
  box-shadow: 0 5px 22px rgba(79,110,247,0.38);
}
.sub-btn:hover:not(:disabled) {
  background-position: 100% 50%;
  box-shadow: 0 8px 34px rgba(79,110,247,0.52);
  transform: translateY(-1px);
}
.sub-btn:active:not(:disabled) {
  transform: translateY(0) scale(0.99);
  box-shadow: 0 4px 16px rgba(79,110,247,0.3);
}
.sub-btn:disabled { opacity: 0.55; cursor: not-allowed; }

.btn-shine {
  position: absolute;
  top: 0; left: -80%; bottom: 0;
  width: 60%;
  background: linear-gradient(90deg, transparent, rgba(255,255,255,0.13), transparent);
  transform: skewX(-20deg);
  pointer-events: none;
}
.sub-btn:hover:not(:disabled) .btn-shine {
  animation: btnShine 0.65s ease forwards;
}
@keyframes btnShine {
  0%   { left: -80%; }
  100% { left: 125%; }
}

.btn-txt {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 9px;
}
.spinner {
  width: 18px; height: 18px;
  animation: spin 0.85s linear infinite;
}
@keyframes spin {
  from { transform: rotate(0deg); }
  to   { transform: rotate(360deg); }
}


.register-entry {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-top: 18px;
  font-size: 13px;
  color: rgba(255,255,255,0.34);
}
.register-entry button {
  border: 0;
  background: transparent;
  color: rgba(212,168,83,0.88);
  font-weight: 700;
  cursor: pointer;
  padding: 4px 6px;
  border-radius: 999px;
  transition: color .2s, background .2s;
}
.register-entry button:hover {
  color: #F2D072;
  background: rgba(212,168,83,0.08);
}
.register-intro {
  border: 1px solid #E8D9B5;
  background: #FFFBEB;
  border-radius: 12px;
  padding: 12px 14px;
  margin-bottom: 16px;
  color: #7C4A03;
}
.register-intro strong { display: block; margin-bottom: 4px; }
.register-intro p { margin: 0; line-height: 1.55; font-size: 13px; }

.form-section-title {
  margin: 16px 0 10px;
  padding-left: 10px;
  border-left: 3px solid #D4A853;
  color: #0F172A;
  font-size: 13px;
  font-weight: 800;
  letter-spacing: .04em;
}
.form-section-title:first-child { margin-top: 2px; }
.register-two-col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.register-two-col :deep(.el-form-item) { margin-bottom: 16px; }
@media (max-width: 640px) { .register-two-col { grid-template-columns: 1fr; gap: 0; } }

.register-form :deep(.el-input__wrapper),
.register-form :deep(.el-textarea__inner) {
  border-radius: 10px;
}

/* Card footer */
.card-ft {
  text-align: center;
  margin-top: 30px;
  padding-top: 20px;
  border-top: 1px solid rgba(255,255,255,0.06);
  font-size: 11px;
  color: rgba(255,255,255,0.16);
}

/* ════════════════════════════════════
   RESPONSIVE
════════════════════════════════════ */
@media (max-width: 1100px) {
  .lp-brand { padding: 52px 52px 52px 60px; }
  .glass-card { padding: 44px 40px 36px; }
}

@media (max-width: 860px) {
  .lp-container { flex-direction: column; min-height: 100vh; }
  .lp-brand {
    flex: 0 0 auto;
    padding: 52px 36px 36px;
    align-items: center;
    text-align: center;
  }
  .b-logo { justify-content: center; }
  .b-desc { max-width: 480px; }
  .conv { justify-content: center; }
  .conv-srcs { grid-template-columns: 1fr 1fr 1fr; gap: 8px 16px; }
  .lp-right { flex: 0 0 auto; padding: 24px 28px 52px; }
  .glass-card { max-width: 440px; margin: 0 auto; }
}

@media (max-width: 540px) {
  .lp-brand { padding: 40px 20px 28px; }
  .b-hl h1  { font-size: clamp(28px, 9vw, 40px); }
  .conv     { display: none; }
  .lp-right { padding: 20px 16px 44px; }
  .glass-card { padding: 38px 24px 30px; border-radius: 18px; }
}
</style>
