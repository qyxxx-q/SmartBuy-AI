<script setup>
import {computed} from 'vue';
const props=defineProps({text:String});
const blocks=computed(()=>{const result=[];let code=false,buffer=[];for(const line of (props.text||'').split('\n')){if(line.startsWith('```')){if(code){result.push({code:true,text:buffer.join('\n')});buffer=[];}code=!code;continue;}if(code){buffer.push(line);continue;}const heading=/^#{1,4}\s/.test(line);result.push({heading,text:line.replace(/^#{1,4}\s+/,'').replace(/^[-*]\s+/,'• ')});}if(buffer.length)result.push({code:true,text:buffer.join('\n')});return result;});
const tokens=text=>text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
</script>
<template><div class="message-text"><template v-for="(block,i) in blocks" :key="i"><pre v-if="block.code">{{block.text}}</pre><div v-else :class="['message-line',block.heading&&'message-heading',!block.text&&'message-space']"><template v-for="(part,j) in tokens(block.text)" :key="j"><strong v-if="part.startsWith('**')">{{part.slice(2,-2)}}</strong><code v-else-if="part.startsWith('`')">{{part.slice(1,-1)}}</code><template v-else>{{part}}</template></template></div></template></div></template>
