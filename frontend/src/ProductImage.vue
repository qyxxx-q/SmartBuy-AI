<script setup>
import {ref,watch} from 'vue';
import UiIcon from './UiIcon.vue';
const props=defineProps({product:Object});const failed=ref(false);watch(()=>props.product?.image_url,()=>failed.value=false);
</script>
<template><div class="product-photo"><img v-if="product?.image_url&&!failed" :src="product.image_url" :alt="product.name+' 官方产品图'" loading="lazy" @error="failed=true"/><UiIcon v-else :name="product?.category==='耳机'?'headphones':product?.category==='相机'?'camera':product?.category==='电脑'?'computer':'phone'" :size="60"/><span v-if="product?.curated&&!failed" class="photo-label">官网产品图</span></div></template>
<style scoped>.product-photo{height:182px;background:#fff;border-radius:12px;display:flex;align-items:center;justify-content:center;position:relative;color:#aaa0ce;overflow:hidden}.product-photo img{width:100%;height:100%;object-fit:contain;padding:12px;mix-blend-mode:multiply}.photo-label{position:absolute;bottom:7px;right:9px;font-size:8px;color:#aaa7b6;background:#ffffffe0;padding:3px 6px;border-radius:4px}</style>
