import assert from 'node:assert/strict';
import {createVoiceInput} from '../src/voiceInput.js';
let draft='原有文字',lastRecognition;
class Recognition{constructor(){lastRecognition=this}start(){this.onstart?.()}stop(){this.onend?.()}abort(){this.onend?.()}}
let voice=createVoiceInput({browser:{SpeechRecognition:Recognition},getDraft:()=>draft,setDraft:v=>draft=v,configured:()=>false,transcribe:()=>assert.fail('浏览器识别不应调用服务转写')});
await voice.start();assert.equal(voice.phase.value,'listening');
lastRecognition.onresult({resultIndex:0,results:[Object.assign([{transcript:'预算两千元'}],{isFinal:true})]});
assert.equal(draft,'原有文字 预算两千元');voice.stop();assert.equal(voice.phase.value,'idle');
assert.ok(voice.notice.value.includes('确认文字'));draft='可以编辑后的文字';await voice.start();voice.cancel();assert.equal(draft,'可以编辑后的文字');voice.dispose();

let permissionCalls=0,stopCalls=0,recorder,resolvePermission;
class Recorder{static isTypeSupported(){return true}constructor(){recorder=this;this.state='inactive';this.mimeType='audio/webm'}start(){this.state='recording'}stop(){this.state='inactive';this.ondataavailable?.({data:new Blob(['audio'])});this.onstop?.()}}
const tracks={getTracks:()=>[{stop:()=>stopCalls++}]};
voice=createVoiceInput({browser:{MediaRecorder:Recorder},media:{getUserMedia:async()=>{permissionCalls++;return tracks}},getDraft:()=>draft,setDraft:v=>draft=v,configured:()=>false,transcribe:async()=>''});
await voice.start();assert.equal(permissionCalls,0);assert.ok(voice.notice.value.includes('配置'));voice.dispose();
let transcriptionResolve,transcriptionCalls=0;draft='保留这段';
voice=createVoiceInput({browser:{MediaRecorder:Recorder},media:{getUserMedia:async()=>tracks},getDraft:()=>draft,setDraft:v=>draft=v,configured:()=>true,transcribe:()=>{transcriptionCalls++;return new Promise(resolve=>transcriptionResolve=resolve)}});
await voice.start();voice.stop();assert.equal(voice.phase.value,'transcribing');assert.equal(transcriptionCalls,1);
voice.cancel();draft='取消后重新编辑';transcriptionResolve('迟到的转写');await Promise.resolve();await Promise.resolve();assert.equal(draft,'取消后重新编辑');assert.ok(stopCalls>0);voice.dispose();
draft='待确认';voice=createVoiceInput({browser:{MediaRecorder:Recorder},media:{getUserMedia:async()=>tracks},getDraft:()=>draft,setDraft:v=>draft=v,configured:()=>true,transcribe:async()=>'识别出的文字'});
await voice.start();voice.stop();await Promise.resolve();await Promise.resolve();assert.equal(draft,'待确认 识别出的文字');assert.equal(voice.phase.value,'idle');voice.dispose();
voice=createVoiceInput({browser:{MediaRecorder:Recorder},media:{getUserMedia:()=>new Promise(resolve=>resolvePermission=resolve)},getDraft:()=>draft,setDraft:v=>draft=v,configured:()=>true,transcribe:()=>assert.fail('取消权限等待后不能转写')});
const pending=voice.start();assert.equal(voice.phase.value,'requesting');voice.cancel();const before=stopCalls;resolvePermission(tracks);await pending;assert.ok(stopCalls>before);assert.equal(voice.phase.value,'idle');voice.dispose();
let streamNumber=0,stopped=[];class DelayedRecorder extends Recorder{stop(){this.state='inactive'}}
voice=createVoiceInput({browser:{MediaRecorder:DelayedRecorder},media:{getUserMedia:async()=>{const id=++streamNumber;return {getTracks:()=>[{stop:()=>stopped.push(id)}]}}},getDraft:()=>draft,setDraft:v=>draft=v,configured:()=>true,transcribe:()=>assert.fail('已取消的录音不能转写')});
await voice.start();const previousRecorder=recorder;voice.cancel();await voice.start();previousRecorder.onstop();assert.equal(voice.phase.value,'listening');assert.ok(!stopped.includes(2));voice.dispose();assert.ok(stopped.includes(2));
console.log('Voice: editable transcript, explicit send boundary, cancellation, late responses and microphone cleanup verified with simulated browser APIs.');
