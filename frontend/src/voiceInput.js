import {ref} from 'vue';
// Explicit start, editable transcript, explicit send. No automatic microphone access.
export function createVoiceInput({browser=globalThis.window||{},media=globalThis.navigator?.mediaDevices,getDraft,setDraft,configured,transcribe}){
 const Recognition=browser.SpeechRecognition||browser.webkitSpeechRecognition;
 const supported=!!Recognition,canRecord=!!media?.getUserMedia&&!!browser.MediaRecorder;
 const mode=ref(supported?'browser':'record'),phase=ref('idle'),notice=ref(''),elapsed=ref(0);
 let recognition,recorder,stream,chunks=[],generation=0,timer,clock,baseDraft='',discard=false;
 function release(){clearTimeout(timer);clearInterval(clock);stream?.getTracks().forEach(t=>t.stop());stream=null;}
 function ticking(){elapsed.value=0;clock=setInterval(()=>elapsed.value++,1000);timer=setTimeout(stop,60000)}
 function cancel(){generation++;discard=true;recognition?.abort();recognition=null;if(recorder?.state==='recording')recorder.stop();release();phase.value='idle';setDraft(baseDraft||'');notice.value='已取消本次语音，内容不会作为聊天消息发送。'}
 async function upload(blob,mime,token){
  if(token!==generation||discard)return;phase.value='transcribing';notice.value='正在转成文字，完成后请确认再发送。';
  try{const text=await transcribe(blob,mime);if(token!==generation)return;setDraft((baseDraft?baseDraft+' ':'')+text);notice.value='转写已完成，可以修改文字后发送。'}catch(e){if(token===generation)notice.value=e.message||'语音转写未成功，可以重试或继续打字。'}finally{if(token===generation)phase.value='idle'}
 }
 function stop(){if(phase.value!=='listening')return;clearTimeout(timer);clearInterval(clock);try{if(mode.value==='browser'){phase.value='finishing';recognition?.stop()}else{phase.value='finishing';if(recorder?.state==='recording')recorder.stop();else{release();phase.value='idle'}}}catch{release();phase.value='idle';notice.value='语音已结束，请确认文字后发送。'}}
 async function start(){
  if(phase.value!=='idle')return;const token=++generation;discard=false;baseDraft=getDraft()||'';notice.value='';
  if(mode.value==='browser'){
   if(!Recognition){notice.value='当前浏览器不支持快速语音识别，可切换录音转文字或打字。';return}
   const rec=new Recognition();recognition=rec;rec.lang='zh-CN';rec.interimResults=true;rec.continuous=false;let final='';
   rec.onstart=()=>{if(token!==generation)return;phase.value='listening';notice.value='正在听，请说话…';ticking()};
   rec.onresult=event=>{if(token!==generation)return;let interim='';for(let i=event.resultIndex;i<event.results.length;i++){if(event.results[i].isFinal)final+=event.results[i][0].transcript;else interim+=event.results[i][0].transcript}setDraft((baseDraft?baseDraft+' ':'')+final+interim)};
   rec.onerror=event=>{if(token!==generation)return;notice.value=({'not-allowed':'麦克风权限未开启，请在浏览器中手动允许后重试。','audio-capture':'没有找到可用麦克风。','no-speech':'没有识别到声音，可以重试或直接打字。',network:'浏览器语音服务连接失败，可切换录音转文字。',aborted:'语音输入已结束。'})[event.error]||'语音识别暂不可用。';release();phase.value='idle'};
   rec.onend=()=>{if(token!==generation)return;release();phase.value='idle';recognition=null;if(!notice.value||notice.value.startsWith('正在听'))notice.value='语音输入已结束，确认文字后再发送。'};
   try{phase.value='requesting';notice.value='正在启动浏览器语音，请按提示确认麦克风权限。';rec.start()}catch{release();phase.value='idle';notice.value='语音输入启动失败，请检查麦克风和浏览器权限。'}
  }else{
   if(!configured()){notice.value='录音转文字需要先配置支持音频转写的模型服务。';return}
   if(!canRecord){notice.value='此浏览器不支持录音，可以切换输入方式或直接打字。';return}
   phase.value='requesting';notice.value='请在浏览器中确认麦克风权限。';
   try{const acquired=await media.getUserMedia({audio:true});if(token!==generation){acquired.getTracks().forEach(t=>t.stop());return}stream=acquired;chunks=[];
    const mime=['audio/webm;codecs=opus','audio/webm','audio/mp4'].find(v=>browser.MediaRecorder.isTypeSupported?.(v));const rec=new browser.MediaRecorder(stream,mime?{mimeType:mime}:undefined);recorder=rec;
    rec.ondataavailable=event=>{if(token===generation&&event.data.size)chunks.push(event.data)};
    rec.onstop=()=>{if(token!==generation||discard)return;release();const type=rec.mimeType||'audio/webm';upload(new Blob(chunks,{type}),type,token)};
    rec.onerror=()=>{if(token!==generation)return;generation++;release();phase.value='idle';notice.value='录音未成功，已停止麦克风。'};
    rec.start();phase.value='listening';notice.value='正在录音。结束后交给已配置服务转写，确认文字后再发送。';ticking();
   }catch{if(token===generation){release();phase.value='idle';notice.value='无法使用麦克风，请手动检查设备和浏览器权限。'}}
  }
 }
 function dispose(){generation++;discard=true;recognition?.abort();if(recorder?.state==='recording')recorder.stop();release();phase.value='idle'}
 return {mode,phase,notice,elapsed,supported,canRecord,start,stop,cancel,dispose};
}
