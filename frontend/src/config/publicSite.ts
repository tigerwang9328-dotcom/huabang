/**
 * 公开品牌官网内容配置。
 * 公开页面从此文件读取文案与展示数据，避免写死在组件里。
 * 注意：此处只放对外宣传内容，严禁出现销售额 / 利润 / 库存 / 会员 / 门店业绩等内部经营数据。
 */

export interface NavItem {
  label: string;
  to: string;
}

export interface ShowcaseItem {
  title: string;
  desc: string;
  image: string; // /images/public/xxx.jpg，缺图时组件自动回退为渐变占位
}

export interface Advantage {
  title: string;
  desc: string;
  icon: string;
}

export interface PublicSiteConfig {
  companyName: string;
  companyEn: string;
  slogan: string;
  heroTitle: string;
  heroSubtitle: string;
  heroIntro: string;
  intro: string;
  brandStory: string;
  advantages: Advantage[];
  products: ShowcaseItem[];
  stores: ShowcaseItem[];
  spaces: ShowcaseItem[];
  nav: NavItem[];
  contact: {
    company: string;
    address: string;
    phone: string;
    email: string;
    hours: string;
  };
}

export const publicSite: PublicSiteConfig = {
  companyName: "华邦服饰",
  companyEn: "HUABANG APPAREL",
  slogan: "专注服装零售与品牌运营",

  heroTitle: "华邦服饰",
  heroSubtitle: "专注服装零售与品牌运营",
  heroIntro: "以门店为基础，以商品为核心，以数据驱动经营增长",

  intro:
    "华邦服饰是一家专注服装零售、门店运营、商品管理和会员服务的服饰企业。公司以线下门店为主要经营阵地，结合线上渠道，持续打造稳定、高效、可复制的服装零售体系。",

  brandStory:
    "华邦从一线门店出发，长期关注顾客真实穿着需求，持续打磨商品结构、门店陈列和服务体验。我们相信，服装不是简单的库存，而是顾客生活方式的一部分。",

  advantages: [
    { title: "多门店运营经验", desc: "覆盖多区域的连锁门店网络，沉淀成熟的零售运营方法论。", icon: "Shop" },
    { title: "稳定商品供应能力", desc: "完善的供应链与商品企划体系，保障货品稳定、上新高效。", icon: "Box" },
    { title: "标准化门店形象", desc: "统一的门店陈列与服务标准，带来一致的品牌体验。", icon: "OfficeBuilding" },
    { title: "数据化经营升级", desc: "以数据驱动选品、陈列与服务，持续提升经营效率。", icon: "TrendCharts" },
  ],

  products: [
    { title: "都市通勤系列", desc: "简约利落，适配多种通勤与商务场景。", image: "/images/public/product-1.jpg" },
    { title: "休闲生活系列", desc: "舒适面料与版型，贴合日常生活穿着。", image: "/images/public/product-2.jpg" },
    { title: "季节主题系列", desc: "顺应季节与潮流，持续上新的主题款式。", image: "/images/public/product-3.jpg" },
  ],

  stores: [
    { title: "城市旗舰门店", desc: "宽敞明亮的购物空间，完整呈现品牌形象。", image: "/images/public/store-1.jpg" },
    { title: "购物中心门店", desc: "位于核心商圈，便捷触达更多顾客。", image: "/images/public/store-2.jpg" },
    { title: "社区精选门店", desc: "贴近社区生活，提供亲切的选购体验。", image: "/images/public/store-3.jpg" },
  ],

  spaces: [
    { title: "品牌展厅", desc: "集中展示当季商品与品牌主张的形象空间。", image: "/images/public/space-1.jpg" },
    { title: "办公与企划中心", desc: "商品企划、运营与设计协同办公的现代空间。", image: "/images/public/space-2.jpg" },
  ],

  nav: [
    { label: "公司简介", to: "/about" },
    { label: "品牌故事", to: "/brand" },
    { label: "产品展示", to: "/products" },
    { label: "门店形象", to: "/stores" },
    { label: "场地展示", to: "/space" },
    { label: "联系我们", to: "/contact" },
  ],

  contact: {
    company: "华邦服饰",
    address: "请在 publicSite.ts 中填写公司地址",
    phone: "400-000-0000",
    email: "contact@huabang.example.com",
    hours: "周一至周日 9:00 - 21:00",
  },
};

export default publicSite;
