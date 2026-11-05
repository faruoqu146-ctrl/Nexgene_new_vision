const API=window.location.origin.replace(/\/$/,''),$=id=>document.getElementById(id);
let csrf='',mode='',idx=0,data={},authMode='login',googleReady=false,phase='asking',saving=false,todayLoaded=false;
const M=[['sleep_duration','How long did you sleep?','Pick the window that feels closest.',[['◔','Under 5h',4.5],['◑','5–6h',5.5],['◒','6–7h',6.5],['◕','7–8h',7.5],['◉','8–9h',8.5],['✦','9h+',9.5]]],['sleep_quality','How did your sleep feel?','No scorekeeping. Just your read.',[['☹','Rough',2],['◔','Restless',4],['◑','Okay',6],['◕','Good',8],['☺','Deep',10]]],['energy','How are you arriving today?','First instinct.',[['🪫','Drained',2],['◔','Low',4],['◑','Steady',6],['◕','Good',8],['⚡','Charged',10]]],['morning_context','Anything unusual?','Optional. You can always skip.',[['○','Nothing unusual','none'],['◌','Headache','headache'],['⌁','Fatigue','fatigue'],['△','Pain','pain'],['→','Skip','skipped']]]];
const E=[['mood','How was today?','The overall texture of the day.',[['☹','Low',2],['◔','Heavy',4],['◑','Mixed',6],['◕','Good',8],['☺','Great',10]]],['stress','Where was your stress?','Today’s signal, not a diagnosis.',[['○','Very low',1],['◔','Low',3],['◑','Moderate',5],['◕','High',7],['●','Very high',9]]],['focus','How was your focus?','How easy was it to stay with things?',[['☁','Scattered',2],['◔','Patchy',4],['◑','Okay',6],['◕','Strong',8],['◎','Locked in',10]]],['activity_level','How much did you move?','Minutes can come later.',[['○','Very little','very_little'],['◔','Light','light'],['◑','Moderate','moderate'],['◕','A lot','high'],['→','Skip','skipped']]],['diet_quality','How did you eat?','Think balance, not calories.',[['·','Chaotic','low'],['◔','Mostly quick','fair'],['◑','Mixed','mixed'],['◕','Mostly balanced','good'],['✦','Very balanced','high']]],['caffeine','Caffeine today?','Coffee, tea and energy drinks count.',[['○','None',0],['◔','1',1],['◑','2',2],['◕','3+',3]]],['alcohol','Alcohol today?','Optional, no judgement.',[['○','None',0],['◔','1',1],['◑','2',2],['◕','3+',3]]],['nicotine','Nicotine / smoking?','Optional context for your baseline.',[['○','None','none'],['◔','Some','some'],['◕','Frequent','frequent']]]];
function node(tag,cls,text){const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n}
function clear(n){while(n.firstChild)n.removeChild(n.firstChild)}
function setMsg(id,text){$(id).textContent=text}
function setAuthMode(next){authMode=next;const reg=next==='register';$('tabLogin').classList.toggle('active',!reg);$('tabRegister').classList.toggle('active',reg);$('authTitle').textContent=reg?'Create your baseline.':'Welcome back.';$('authLead').textContent=reg?'A private place for your signals to become useful.':'Your baseline is waiting where you left it.';$('authPrimary').textContent=reg?'Create account':'Sign in';$('passwordRules').classList.toggle('hide',!reg);$('password').setAttribute('autocomplete',reg?'new-password':'current-password');setMsg('authmsg','');}
function togglePassword(){const input=$('password'),button=document.querySelector('.passwordField button');const shown=input.type==='text';input.type=shown?'password':'text';button.textContent=shown?'Show':'Hide'}
async function account(){if(csrf){const r=await fetch(API+'/api/v1/auth/logout',{method:'POST',headers:{'X-CSRF-Token':csrf}});if(r.ok){csrf='';$('account').textContent='Sign in';location.reload()}}else{$('auth').classList.remove('hide');setAuthMode('login');await initGoogle()}}
async function finishAuth(){await fetch(API+'/api/v1/auth/csrf');csrf=document.cookie.split('; ').find(x=>x.startsWith('nexgene_csrf='))?.split('=')[1]||'';$('auth').classList.add('hide');$('account').textContent='Sign out';await loadProfile();await load()}
async function submitAuth(){const email=$('email').value.trim().toLowerCase(),password=$('password').value;if(!email||password.length<12||!/[a-z]/.test(password)||!/[A-Z]/.test(password)||!/[0-9]/.test(password)||!/[^A-Za-z0-9]/.test(password)){setMsg('authmsg','Use a valid email and a 12+ character password with upper, lower, number and symbol.');return}setMsg('authmsg','');$('authPrimary').disabled=true;try{const path=authMode==='register'?'/api/v1/auth/register':'/api/v1/auth/login';const r=await fetch(API+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,password})});let d={};try{d=await r.json()}catch{}if(!r.ok){setMsg('authmsg',d.detail||'Could not authenticate.');return}await finishAuth()}catch(e){setMsg('authmsg','NexGene could not reach the server right now.')}finally{$('authPrimary').disabled=false}}
function register(){setAuthMode('register')}function login(){setAuthMode('login')}
async function initGoogle(){if(googleReady)return;try{const cfg=await fetch(API+'/api/v1/auth/google/config').then(r=>r.json());if(!cfg.enabled||!cfg.client_id){$('googleNote').textContent='Google sign-in can be enabled for this deployment.';return}if(!window.google){await new Promise((resolve,reject)=>{const sc=document.createElement('script');sc.src='https://accounts.google.com/gsi/client';sc.async=true;sc.defer=true;sc.onload=resolve;sc.onerror=reject;document.head.appendChild(sc)})}window.handleGoogleCredential=async function(response){setMsg('authmsg','');try{const r=await fetch(API+'/api/v1/auth/google',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({credential:response.credential})});const d=await r.json().catch(()=>({}));if(!r.ok){setMsg('authmsg',d.detail||'Could not authenticate with Google.');return}await finishAuth()}catch(e){setMsg('authmsg','Google sign-in could not be completed right now.')}};google.accounts.id.initialize({client_id:cfg.client_id,callback:window.handleGoogleCredential,use_fedcm_for_prompt:true});google.accounts.id.renderButton($('googleButton'),{type:'standard',theme:'outline',size:'large',text:'continue_with',shape:'rectangular',logo_alignment:'left',width:330});googleReady=true}catch(e){$('googleNote').textContent='Google sign-in is unavailable in this environment.'}}
async function loadProfile(){const d=await get('/api/v1/profile');if(!d.complete){$('onboarding').classList.remove('hide');const p=d.profile||{};['age_range','country','occupation','study_field','schedule','timezone'].forEach(k=>{if($(k))$(k).value=p[k]||''});if($('student'))$('student').value=p.student===true?'yes':p.student===false?'no':''}else $('onboarding').classList.add('hide')}
async function saveProfile(){const payload={age_range:$('age_range').value.trim()||null,country:$('country').value.trim()||null,occupation:$('occupation').value.trim()||null,student:$('student').value===''?null:$('student').value==='yes',study_field:$('study_field').value.trim()||null,schedule:$('schedule').value||null,timezone:$('timezone').value.trim()||null};try{const r=await fetch(API+'/api/v1/profile',{method:'PUT',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(payload)});const d=await r.json();if(!r.ok){setMsg('profilemsg',d.detail||'Could not save your context.');return}$('onboarding').classList.add('hide');setMsg('profilemsg','');await loadReport()}catch(e){setMsg('profilemsg','Could not save your context right now.')}}
function start(m){if(!csrf){$('auth').classList.remove('hide');setMsg('authmsg','Create an account first. Your check-ins need somewhere private to live.');return}mode=m;idx=0;data={};phase='asking';saving=false;showAsking();$('sheet').classList.remove('hide');render()}
function render(){const arr=mode==='morning'?M:E,item=arr[idx];$('step').textContent=`${idx+1} / ${arr.length}`;const q=$('q');clear(q);q.append(node('div','k',`${mode} check-in`),node('h3',null,item[1]),node('p',null,item[2]));const choices=$('choices');clear(choices);item[3].forEach(o=>{const b=node('button','choice'),i=node('i',null,o[0]),label=node('b',null,o[1]);b.append(i,label);b.onclick=()=>{choices.querySelectorAll('.choice').forEach(x=>x.classList.remove('sel'));b.classList.add('sel');data[item[0]]=o[2];$('next').disabled=false};choices.appendChild(b)});$('next').disabled=data[item[0]]===undefined;$('next').textContent=idx===arr.length-1?'Save':'Continue'}
function showAsking(){clear($('sheetStatus'));$('q').classList.remove('hide');$('choices').classList.remove('hide');$('next').classList.remove('hide')}
function showSheetStatus(){$('q').classList.add('hide');$('choices').classList.add('hide')}
async function nextStep(){
  if(phase==='saved'){closeSheet();return}
  const arr=mode==='morning'?M:E;
  if(idx<arr.length-1){idx++;render();return}
  await submitCheckin();
}
async function submitCheckin(){
  if(saving)return;
  saving=true;showSheetStatus();$('next').disabled=true;$('next').textContent='Saving…';
  NexGeneProgressive.renderSaving(document,$('sheetStatus'));
  // a skipped answer is not an observation; the server drops it too, so nothing is stored for it
  const values={};Object.keys(data).forEach(k=>{if(data[k]!=='skipped')values[k]=data[k]});
  const res=await NexGeneApi.apiRequest(`${API}/api/v1/checkins/${mode}`,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({values}),timeoutMs:20000,validate:d=>d&&typeof d.saved==='number'});
  saving=false;
  if(res.state==='unauthorized'){closeSheet();sessionExpired();return}
  if(res.state!=='ready'){
    NexGeneProgressive.renderSaveError(document,$('sheetStatus'),res,{retry:()=>submitCheckin(),check:()=>{closeSheet();load()}});
    $('next').textContent='Save';$('next').disabled=true;return}
  phase='saved';$('step').textContent='Saved';
  NexGeneProgressive.renderSaved(document,$('sheetStatus'),res.data);
  $('next').disabled=false;$('next').textContent='Done';
  // Today updates from the response itself (no waiting, no reload); a background refresh then reconciles with the server.
  if(res.data.feedback&&NexGeneProgressive.validate(res.data.feedback))applyProgressive(res.data.feedback);
  loadToday(true);
}
function closeSheet(){$('sheet').classList.add('hide');phase='asking';saving=false;showAsking()}
async function get(p){if(!csrf)return{};const r=await fetch(API+p);if(r.status===401){csrf='';$('account').textContent='Sign in';$('auth').classList.remove('hide');setMsg('authmsg','Your session expired. Please sign in again.');return{}}return r.ok?r.json():{}}
function showView(v){['today','patterns','timeline','report','research'].forEach(x=>{$(x+'View').classList.toggle('hide',x!==v);const n=$('n'+x[0].toUpperCase()+x.slice(1));if(n)n.classList.toggle('active',x===v)});if(v==='patterns')loadPatterns();if(v==='timeline')loadTimeline();if(v==='report')loadReport();if(v==='research')loadResearch()}
function applyProgressive(d){
  const P=NexGeneProgressive,handlers={checkIn:m=>start(typeof m==='string'?m:(new Date().getHours()<15?'morning':'evening')),patterns:()=>showView('patterns'),report:()=>showView('report'),research:()=>showView('research')};
  P.renderSnapshot(document,$('snapshot'),d.today,handlers);P.renderProgress(document,$('count'),$('bar'),d.today,$('countDetail'));
  P.renderInterpretation(document,$('insight'),d.today);P.renderLevels(document,$('levels'),d);
  P.renderSignals(document,$('signals'),d.signals,handlers);P.renderNext(document,$('nextObs'),d.next_observations,handlers);
  todayLoaded=true;
}
function todayFailure(res){
  // An API failure is NOT an empty day. Keep whatever is already on screen and say plainly that it may be out of date.
  const box=$('snapshot'),m=NexGeneApi.messageFor(res),card=node('div','empty loadFailure');card.append(node('b',null,m.title),node('span',null,m.body+(todayLoaded?' What you see may be out of date.':'')));
  if(res.requestId)card.appendChild(node('small',null,'Ref '+res.requestId));
  const b=node('button',null,'TRY AGAIN');b.onclick=()=>loadToday();card.appendChild(b);
  const old=box.querySelector('.loadFailure');if(old)old.remove();
  if(todayLoaded)box.insertBefore(card,box.firstChild);else{clear(box);box.appendChild(card)}
}
async function loadToday(quiet){
  if(!csrf)return;
  if(!todayLoaded&&!quiet)NexGeneProgressive.renderLoading(document,$('snapshot'),'Loading today');
  const res=await NexGeneApi.apiRequest(API+'/api/v1/intelligence/progressive',{validate:NexGeneProgressive.validate});
  if(res.state==='unauthorized'){sessionExpired();return}
  if(res.state!=='ready'){todayFailure(res);return}
  applyProgressive(res.data);$('account').textContent='Sign out';
}
async function load(){await loadToday()}
async function loadPatterns(){
  const cards=$('patternCards'),chart=$('chart'),notes=$('patternNotes');
  NexGeneProgressive.renderLoading(document,cards,'Loading patterns');
  const [pat,prog]=await Promise.all([NexGeneApi.apiRequest(API+'/api/v1/patterns',{validate:NexGeneProgressive.validatePatterns}),NexGeneApi.apiRequest(API+'/api/v1/intelligence/progressive',{validate:NexGeneProgressive.validate})]);
  if(pat.state==='unauthorized'||prog.state==='unauthorized'){sessionExpired();return}
  if(pat.state!=='ready'){showFailure(cards,pat,loadPatterns);clear(chart);clear(notes);return}
  NexGeneProgressive.renderPatterns(document,cards,chart,notes,pat.data,prog.state==='ready'?prog.data:null);
  if(prog.state!=='ready'){const m=NexGeneApi.messageFor(prog);notes.appendChild(node('p','reportNote','Early-pattern notes could not be loaded. '+m.body))}
}
function signedOutToday(){todayLoaded=false;['snapshot','signals','nextObs'].forEach(id=>{const b=$(id);clear(b);if(id==='snapshot'){const e=node('div','empty');e.append(node('b',null,'Sign in to see your day.'),node('span',null,'Your check-ins are private to your account.'));b.appendChild(e)}})}
function sessionExpired(){csrf='';$('account').textContent='Sign in';$('auth').classList.remove('hide');setMsg('authmsg','Your session expired. Please sign in again.');signedOutToday()}
function showFailure(box,res,retry){
  const m=NexGeneApi.messageFor(res),had=box.querySelector('.event,.reportCard,.metric,.signal,.pattern,.rSection');
  if(res.state==='unauthorized'){sessionExpired();return}
  const card=node('div','empty');card.append(node('b',null,m.title),node('span',null,m.body));
  if(res.requestId)card.appendChild(node('small',null,'Ref '+res.requestId));
  if(res.retryable&&retry){const b=node('button',null,'TRY AGAIN');b.onclick=retry;card.appendChild(b)}
  if(had){const old=box.querySelector('.loadFailure');if(old)old.remove();card.classList.add('loadFailure');box.insertBefore(card,box.firstChild)}
  else{clear(box);box.appendChild(card)}
}
async function loadTimeline(){
  const timeline=$('timeline');
  const res=await NexGeneApi.apiRequest(API+'/api/v1/timeline',{validate:Array.isArray,isEmpty:d=>d.length===0});
  if(res.state==='ready'){clear(timeline);res.data.slice(0,60).forEach(r=>{const e=node('div','event');e.append(node('span',null,new Date(r.observed_at||r.recorded_at).toLocaleDateString()),node('b',null,r.kind.replaceAll('_',' ')),node('em',null,String(r.value)));timeline.appendChild(e)});return}
  if(res.state==='empty'){clear(timeline);const e=node('div','empty');e.append(node('b',null,'No observations yet.'),node('span',null,'Your first check-in will appear here.'));timeline.appendChild(e);return}
  showFailure(timeline,res,loadTimeline);
}
const ENGINE_NOTE={not_run:'The research engine has not run yet, so no engine-tested patterns are shown.',running:'A research run is in progress.',interrupted:'The last research run was interrupted; no engine results are shown.',failed:'The last research run failed; no engine results are shown.',stale:'Engine results shown come from an earlier run.',no_eligible_findings:'The research engine ran; nothing met the bar for reporting.',current:''};
function profileContext(d){if(d.profile?.occupation||d.profile?.student!==null&&d.profile?.student!==undefined){const context=node('div','reportContext');let label=d.profile.occupation||'Student';if(d.profile.student===true&&d.profile.study_field)label+=' · '+d.profile.study_field;context.append(node('small',null,'YOUR CONTEXT'),node('b',null,label));return context}return null}
function renderLegacyReport(box,d){
  // Only used when the server predates the progressive `layout` (e.g. mid-rollout). Same content as before.
  clear(box);const insufficient=d.report_state==='insufficient_data';
  const hero=node('div','reportHero');hero.append(node('div','eyebrow',insufficient?'NOT ENOUGH DATA YET':String(d.coverage.days)+' DAYS OF SIGNAL'),node('h2',null,d.title||'Your week with NexGene'),node('p',null,d.subtitle||''));box.appendChild(hero);
  (d.data_quality_warnings||[]).forEach(w=>box.appendChild(node('p','reportNote',w.message)));
  const ctx=profileContext(d);if(ctx)box.appendChild(ctx);
  (d.sections||[]).forEach(sec=>{const card=node('article','reportCard');card.append(node('small',null,(sec.kind||'note').replaceAll('_',' ').toUpperCase()),node('h3',null,sec.title),node('p',null,sec.body));box.appendChild(card)});
  if(d.experiment){const ex=node('article','reportCard experiment');ex.append(node('small',null,'AN OBSERVATION TO TRY'),node('h3',null,'Next week'),node('p',null,d.experiment));box.appendChild(ex)}
}
async function loadReport(){const box=$('reportContent');if(!box)return;
  if(!box.firstChild)NexGeneProgressive.renderLoading(document,box,'Loading your week');
  const res=await NexGeneApi.apiRequest(API+'/api/v1/reports/weekly',{validate:d=>NexGeneProgressive.validateReport(d)||(d&&(d.status==='not_ready'||(d.status==='ready'&&Array.isArray(d.sections)&&d.coverage))),isEmpty:d=>!Array.isArray(d.layout)&&d.status==='not_ready'});
  if(res.state==='empty'){clear(box);box.append(node('div','reportHero',res.data.message||'No observations in the last 7 days yet.'));return}
  if(res.state!=='ready'){showFailure(box,res,loadReport);return}
  const d=res.data;
  if(Array.isArray(d.layout)){NexGeneProgressive.renderReportLayout(document,box,d);const ctx=profileContext(d);if(ctx)box.insertBefore(ctx,box.children[1]||null)}
  else renderLegacyReport(box,d);
  const es=ENGINE_NOTE[d.engine&&d.engine.state];if(es)box.appendChild(node('p','reportNote',es));
  await appendAiCard(box);box.appendChild(node('p','reportNote',d.disclaimer||''));
}
async function appendAiCard(box){
  const ai=node('article','reportCard aiCard');const aiTitle=node('h3',null,'AI-assisted read');const aiText=node('p',null,'Optional. If enabled, NexGene can use an AI model to turn the same bounded weekly evidence into a warmer narrative. Your choice stays off by default.');const aiRow=node('div','aiRow');const aiToggle=node('button',null,'CHECK AI SETTINGS');aiToggle.onclick=()=>configureAI();aiRow.appendChild(aiToggle);ai.append(aiTitle,aiText,aiRow);box.appendChild(ai);
  try{const cfg=await get('/api/v1/ai/settings');if(cfg.enabled){const gen=node('button','aiGenerate','READ THIS WEEK WITH AI');gen.onclick=async()=>{gen.disabled=true;gen.textContent='READING…';try{const out=await get('/api/v1/reports/weekly/ai');if(out.report){const card=node('article','reportCard aiOutput');card.append(node('small',null,'AI-ASSISTED'),node('p',null,out.report));box.insertBefore(card,ai)}else alert(out.message||'Not enough signal yet.')}catch(e){alert('AI report could not be generated right now.')}finally{gen.disabled=false;gen.textContent='READ THIS WEEK WITH AI'}};aiRow.appendChild(gen)}}catch(e){box.appendChild(node('p','reportNote','AI settings could not be checked right now. The report above is unaffected.'))}
}
let researchRunHash=null;
async function loadResearch(){
  const box=$('researchContent');if(!box)return;
  if(!csrf){clear(box);const e=node('div','empty');e.append(node('b',null,'Sign in to see your research report.'),node('span',null,'Nothing is shown until your account is verified.'));box.appendChild(e);return}
  const res=await NexGeneApi.apiRequest(API+'/api/v1/intelligence/engine/status',{validate:NexGeneResearch.validateStatus});
  if(res.state!=='ready'){showFailure(box,res,loadResearch);return}
  const m=res.data.last_run&&res.data.last_run.manifest;researchRunHash=(m&&m.run_hash)||null;
  NexGeneResearch.renderResearch(document,box,res.data,{onRun:runResearch,onAudit:loadAudit,onHistory:loadHistory});
}
async function runResearch(btn){
  btn.disabled=true;btn.textContent='RUNNING…';
  const res=await NexGeneApi.apiRequest(API+'/api/v1/intelligence/engine/run',{method:'POST',headers:{'X-CSRF-Token':csrf},timeoutMs:120000,validate:d=>d&&typeof d==='object'&&!!d.manifest});
  if(res.state==='unauthorized'){sessionExpired();return}
  const text=res.state==='ready'?'':NexGeneResearch.runMessage(res);
  await loadResearch();
  const out=document.querySelector('#researchContent .rsRunMsg');if(out&&text)out.textContent=text;
}
async function loadAudit(id,into,btn){
  btn.disabled=true;
  const res=await NexGeneApi.apiRequest(API+'/api/v1/intelligence/audit/'+encodeURIComponent(id),{validate:d=>d&&typeof d==='object'&&!!d.hypothesis});
  btn.disabled=false;
  if(res.state==='unauthorized'){sessionExpired();return}
  if(res.state!=='ready'){clear(into);const m=NexGeneApi.messageFor(res);into.appendChild(node('p','reportNote',m.title+'. '+m.body));return}
  NexGeneResearch.renderAudit(document,into,res.data,researchRunHash);
}
async function loadHistory(into,btn){
  btn.disabled=true;
  const res=await NexGeneApi.apiRequest(API+'/api/v1/intelligence/research/manifest',{validate:d=>d&&Array.isArray(d.manifests)});
  btn.disabled=false;
  if(res.state==='unauthorized'){sessionExpired();return}
  if(res.state!=='ready'){clear(into);const m=NexGeneApi.messageFor(res);into.appendChild(node('p','reportNote',m.title+'. '+m.body));return}
  NexGeneResearch.renderHistory(document,into,res.data);
}
async function configureAI(){try{const cfg=await get('/api/v1/ai/settings');if(!cfg.available){alert('AI analysis is not configured for this deployment yet.');return}const enable=confirm(cfg.enabled?'Turn off AI-assisted weekly reports?':'Turn on optional AI-assisted weekly reports? This sends the bounded weekly report evidence to the configured AI provider.');const r=await fetch(API+'/api/v1/ai/settings',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({enabled:enable})});if(r.ok)await loadReport()}catch(e){alert('AI settings could not be updated right now.')}}
async function boot(){const d=new Date();$('date').textContent=d.toLocaleDateString(undefined,{day:'2-digit',month:'short'}).toUpperCase();$('greeting').textContent=d.getHours()<12?'Good morning,':d.getHours()<18?'Good afternoon,':'Good evening,';initGoogle();if(document.cookie.includes('nexgene_csrf=')){NexGeneProgressive.renderLoading(document,$('snapshot'),'Loading today');NexGeneProgressive.renderLoading(document,$('signals'),'Loading signals');await fetch(API+'/api/v1/auth/csrf');csrf=document.cookie.split('; ').find(x=>x.startsWith('nexgene_csrf='))?.split('=')[1]||'';$('account').textContent='Sign out';const me=await get('/api/v1/auth/me');if(me.id){await loadProfile();await load()}else{csrf='';signedOutToday()}}}boot();
