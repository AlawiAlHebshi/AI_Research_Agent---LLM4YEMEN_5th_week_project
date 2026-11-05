(() => {
  'use strict';
  const G = window.GUIDE;
  const SOURCES = window.SOURCE_INDEX || {};
  const NOTES = window.FUNCTION_NOTES || {};
  const $ = selector => document.querySelector(selector);
  const esc = value => String(value ?? '').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll(String.fromCharCode(34),'&quot;').replaceAll(String.fromCharCode(39),'&#39;');
  const normalize = text => String(text).toLowerCase().replace(/[أإآ]/g,'ا').replace(/[\u064b-\u065f]/g,'');
  const file = id => G.files.find(item => item.id === id);
  const link = id => '#file/' + encodeURIComponent(id);
  const chip = id => `<a class='chip' href='${link(id)}'>${esc(file(id)?.name || id)}</a>`;
  let read = new Set();
  try { read = new Set(JSON.parse(localStorage.getItem('research-guide-read-v1') || '[]').filter(id => file(id))); } catch (_) {}
  const state = {route:'home', search:'', journey:0, mode:'scientific', scenario:'recovery', save:'no', answers:{}};
  const pages = [
    ['home','ابدأ من هنا'], ['map','خريطة الملفات'], ['journey','رحلة سؤال — خطوة بخطوة'],
    ['testing','كيف أشغّل وأختبر؟'], ['terms','الكلمات ببساطة'], ['quiz','اختبر فهمك'], ['roadmap','الموجود والخطط المقبلة'], ['about','عن هذا الدليل']
  ];
  const intro = (kicker,title,description) => `<div class='eyebrow'>${kicker}</div><h1>${title}</h1><p class='lead'>${description}</p>`;
  const note = (title,text,warn=false) => `<div class='note ${warn?'warn':''}'><strong>${title}</strong>${text}</div>`;
  const command = (text,paid=false) => `<div class='facts'><span class='pill ${paid?'gold':'gray'}'>${paid?'عند تنفيذه: إنترنت ورصيد النموذج':'دون استدعاء نموذج'}</span></div><div class='command'><code>${esc(text)}</code><button class='copy' data-copy='${esc(text)}'>نسخ الأمر</button></div>`;
  const fileCard = (item,index='') => `<a class='card filecard' href='${link(item.id)}'><span class='arrow' aria-hidden='true'>←</span><span class='card-num'>${index ? String(index).padStart(2,'0') : 'FILE'}</span><span class='filename'>${esc(item.name)}</span><h3>${esc(item.role)}</h3><p>${esc(item.intro)}</p></a>`;

  function updateProgress() {
    $('#progress-label').textContent = `${read.size} من ${G.files.length} ملفًا ومجلدًا فُهمت`;
    $('#progress-fill').style.width = (read.size / G.files.length * 100) + '%';
  }

  function renderNav() {
    const q = normalize(state.search);
    let html = `<div class='nav-group'><div class='nav-label'>طريقك إلى فهم المشروع</div>${pages.map(([id,title]) => `<a href='#${id}' class='${state.route===id?'active':''}'>${title}<span aria-hidden='true'>${id==='journey'?'↗':'·'}</span></a>`).join('')}</div>`;
    let found = 0;
    G.groups.forEach((group,index) => {
      const items = G.files.filter(item => item.group===index && (!q || normalize([item.name,item.role,item.intro,...item.steps,...(SOURCES[item.id]?.nodes || []).map(node=>node.qualified)].join(' ')).includes(q)));
      if (!items.length) return;
      found += items.length;
      html += `<div class='nav-group'><div class='nav-label'>${esc(group)} <span> / ${items.length}</span></div>${items.map(item => `<a href='${link(item.id)}' class='${state.route==='file/'+item.id?'active':''}' title='${esc(item.role)}'><span class='filename'>${esc(item.name)}</span><span class='tick'>${read.has(item.id)?'✓':''}</span></a>`).join('')}</div>`;
    });
    if (q && !found) html += `<div class='empty'>لا توجد ملفات مطابقة. جرّب اسمًا مثل budget أو كلمة مثل الحفظ.</div>`;
    $('#nav').innerHTML = html;
    updateProgress();
  }

  function renderHome() {
    return `<div class='hero'><div><div class='eyebrow'>من السؤال إلى التقرير… افهم الطريق</div><h1>افهم مشروعك،<br>ملفًا بملف.</h1><p>دليل عربي يشرح ماذا يفعل الكود، ومن المسؤول عن كل خطوة. ابدأ بالصورة العامة، ثم افتح الملف الذي تريد فهمه.</p><div class='actions'><a class='btn' href='#journey'>امشِ مع سؤال تجريبي ←</a><a class='btn secondary' href='${link('main.py')}'>ابدأ بـ main.py</a></div></div><div class='hero-illustration' aria-label='فكرة مبسطة: سؤال ثم بحث ثم تقرير'><div class='diagram-bar'><span class='dot'></span><b>main.py</b><span>يستقبل ويرتب</span></div><div class='diagram-bar'><span class='dot'></span><b>tools.py</b><span>يجمع المصادر</span></div><div class='diagram-bar'><span class='dot'></span><b>budget.py</b><span>يحمي الرصيد</span></div><div class='hero-note'>أجزاء صغيرة تتعاون لأداء مهمة واحدة.</div></div></div>
    ${note('فكرة المشروع في جملة','تكتب سؤالًا، فيختار النموذج أدوات بحث مسموحة، وينفذها برنامج Python، ثم يعرض إجابة بمصادرها ويمكن حفظها بعد موافقتك.')}
    <section class='section'><div class='section-head'><h2>ابدأ بهذه الملفات الثلاثة</h2><a class='small' href='#map'>كل الملفات ←</a></div><div class='grid'>${['main.py','tools.py','budget.py'].map((id,i)=>fileCard(file(id),i+1)).join('')}</div></section>
    <section class='section'><div class='section-head'><h2>من يفعل ماذا؟</h2></div><div class='grid two'><div class='card'><h3>النموذج يفكر ويكتب</h3><p>يفهم سؤالك، ويقترح أداة، ثم يقرأ نتائجها ويصوغ الإجابة. لا ينفذ دوال Python بمجرد كتابة اسمها.</p></div><div class='card'><h3>البرنامج ينفّذ ويتحقق</h3><p>يقرر ما هو مسموح، ويرسل الطلبات، ويتتبع التكلفة، ويرفض الروابط غير المسترجعة، ويسأل عن الحفظ.</p></div></div></section>
    <section class='section'><div class='section-head'><h2>رحلة البحث في ثماني محطات</h2></div>${flowCards()}</section>
    <section class='section'><div class='grid two'><div class='card'><span class='pill'>قراءة آمنة</span><h3>هذا الدليل لا يجري بحثًا</h3><p>كل الأمثلة التفاعلية تعليمية. لا يرسل الموقع طلبات للنموذج، ولا يقرأ .env، ولا يشغل أوامر الطرفية.</p></div><div class='card'><span class='pill gold'>حالة المشروع</span><h3>ما بعد المهمتين 3 و4</h3><p>البحث العلمي والتتبع موجودان. MCP وذاكرة SQLite ما زالا خطة للمهمة 5، ومراجعة الأمان الأوسع خطة للمهمة 6.</p><a class='small' href='#roadmap'>اعرف ما أُنجز وما بقي ←</a></div></div></section>`;
  }

  function flowCards() {
    const entries = [
      ['تستقبل السؤال','main.py'],['تختار النمط','main.py'],['تفحص الميزانية','budget.py'],['تستدعي أداة','tools.py'],
      ['تجهز الأدلة','research_models.py'],['تتحقق من الجواب','main.py'],['تسأل عن الحفظ','tools.py'],['تسجل النهاية','tracing.py']
    ];
    return `<div class='flow-grid'>${entries.map(([label,id],i)=>`<a class='flow-item' href='${link(id)}'><span class='step-n'>${String(i+1).padStart(2,'0')}</span><strong>${label}</strong><small><bdi>${id}</bdi></small></a>`).join('')}</div>`;
  }

  function renderMap() {
    return intro('خريطة المشروع','كل ملف له مهمة.','لا تحتاج فهم كل الملفات مرة واحدة. ابدأ بالتشغيل، ثم الأدوات والبيانات، ثم الميزانية والسجل، وأخيرًا الاختبارات.') +
      G.groups.map((group,index)=>`<section class='section'><div class='section-head'><h2>${group}</h2><span class='muted small'>${G.files.filter(item=>item.group===index).length} ملفًا ومجلدًا</span></div><div class='grid'>${G.files.filter(item=>item.group===index).map((item,i)=>fileCard(item,i+1)).join('')}</div></section>`).join('') +
      note('كيف تقرأ خريطة العلاقات؟','main.py يستعمل بقية الأجزاء. scientific_tools.py يستفيد من tools.py للحفظ وسياق المهمة، ومن research_models.py لترتيب الأوراق. budget.py وtracing.py يخدمان الرحلة كلها.');
  }

  function functionNote(node) {
    if (node.name==='main' && state.route==='file/scripts/check_scientific_sources.py') return 'يختار مصادر الفحص، ويجربها دون مفاتيح أو OpenAI، ثم يطبع حالتها وعدد الطلبات ومسار السجل.';
    if (node.name==='main' && state.route==='file/scripts/export_trace.py') return 'يقرأ مسار سجل وتصنيفه، ثم يطلب تصديره أو يعرض سبب الرفض دون إعادة البحث.';
    if (NOTES[node.qualified]) return NOTES[node.qualified];
    if (NOTES[node.name]) return NOTES[node.name];
    if (node.name.startsWith('test_')) return testNote(node.name);
    if (node.qualified.startsWith('SafeConsoleCallback.')) return node.name==='on_tool_end'?'يسجل اكتمال الأداة دون عرض محتوى النتيجة الخام.':'يتعامل مع إشعار من خطوات الوكيل مع منع عرض بيانات خام غير لازمة.';
    if (node.kind==='class') return 'يجمع إعدادات ودوال هذا الجزء. افتح تفاصيل الدوال التابعة له أدناه لتتبع عملها.';
    return 'جزء مساعد في ترتيب سيناريو الاختبار وتنفيذه؛ لا يستدعي خدمة حقيقية بمفرده.';
  }

  function testNote(name) {
    const rules = [
      ['two_processes','يتحقق أن عمليتين لا تستطيعان إنفاق الرصيد المتبقي نفسه.'],['happy_path','يتحقق من نجاح المسار المعتاد بالنتائج الوهمية المتوقعة.'],
      ['429','يتحقق من الانتقال إلى OpenAlex عند تقييد Semantic Scholar.'],['five','يجرب عدة أسئلة للتأكد من استمرار المسار المسموح.'],
      ['citation','يرفض أرقام مراجع غير صالحة أو مفقودة.'],['duplicate','يفحص التكرار أو السجلات المكررة حتى لا تُحتسب مرتين.'],
      ['different_dois','يتأكد أن ورقتين بمعرّفين مختلفين لا تُدمجان لمجرد تشابه العنوان.'],['refusal','يتأكد أن رفض الحفظ لا ينشئ تقريرًا.'],
      ['permission_accepts','يتأكد أن الموافقة تحفظ التقرير المتحقق فقط.'],['queued','يتأكد أن طلب الحفظ أثناء البحث لا يكتب ملفًا.'],
      ['paths','يرفض أسماء الملفات والمسارات غير المسموحة.'],['linked','يرفض مجلد حفظ مرتبطًا بمسار آخر.'],
      ['untrusted','يتأكد أن التعليمات الواردة من مصدر لا تتحول إلى موافقة حفظ.'],['secret','يفحص تنقية أنماط الأسرار والروابط غير المقبولة.'],
      ['keys','يفحص أن المفاتيح الوهمية لا تصل للسجلات أو للفحص العام بلا مفاتيح.'],['missing_usage','يوقف المهمة عند غياب الاستهلاك ويُبقي الحجز.'],
      ['invalid_usage','يرفض أعداد الاستهلاك غير الصالحة دون إلغاء الحجز.'],['transport_failure','يتأكد أن انقطاع الاتصال لا يسبب إعادة طلب تلقائية.'],
      ['tenth','يتحقق أن حلقة النموذج تتوقف عند عشر استدعاءات.'],['eleventh','يمنع الاستدعاء الحادي عشر قبل نقله للخدمة.'],
      ['caps','يفحص حدود المهمة واليوم والإجمالي قبل إرسال طلب.'],['restart','يتأكد أن سجل الإنفاق يستمر بعد إعادة فتحه.'],
      ['missing_previous','يرفض بدء رصيد جديد عندما يُفقد سجل سابق.'],['corrupt','يرفض سجلًا تالفًا دون تصفيره.'],
      ['snapshot','يتأكد أن قراءة الرصيد لا تغيّر ملفه.'],['cache','يتأكد أن تكرار الاستعلام لا يكرر اتصال المصدر.'],
      ['xml','يفحص رفض رد XML تالف أو غير آمن.'],['no_pdf','يتأكد أن طلب arXiv لا ينزّل ملف PDF.'],
      ['spacing','يتحقق من فاصل طلبات arXiv باستخدام وقت وهمي.'],['position','يفحص إعادة ترتيب كلمات الملخص ورفض الخريطة غير الصالحة.'],
      ['no_abstract','يتأكد أن الورقة بلا ملخص ليست دليلًا على نتائجها.'],['clipping','يتأكد من بيان اختصار الملخص.'],
      ['ten_paper','يفحص حد عشر أوراق مختلفة داخل المهمة.'],['crowd_out','يتأكد أن سجلات بلا ملخص لا تزاحم الأدلة المتاحة.'],
      ['missing_authors','يقبل ورقة مفيدة رغم غياب المؤلفين، ويستخدم رابطًا صالحًا متاحًا.'],['missing_metadata','يتجاهل سجلًا غير صالح ويحتفظ بالسجلات المفيدة.'],
      ['mode','يفحص أن لكل نمط أدواته المسموحة.'],['prompt','يتحقق من التعليمات أو رفض تسجيل محتوى غير مسموح.'],
      ['invented','يرفض رابطًا لم ترجعه الأدوات.'],['unretrieved','يرفض رابطًا غير مسترجع داخل نص الإجابة.'],
      ['empty_search','يتأكد أن النتائج الفارغة لا تكفي لادعاء إجابة موثقة.'],['invalid_json','يتعامل مع رد غير صالح دون استدعاء إصلاح مدفوع.'],
      ['schema','يفحص شكل السجل وتسلسله وتنقية قيمه.'],['unknown_fields','يرفض حقولًا غير مصرح بتسجيلها.'],
      ['malformed','يرفض سجل JSONL مبتورًا أو غير صالح.'],['overwrites','يمنع استبدال سجل سابق.'],
      ['promoted','يمنع تقديم سجل محاكاة كدليل حي.'],['public_probe','يمنع تقديم فحص الأدوات وحده كنجاح كامل للوكيل.'],
      ['trace_failure','يمنع الاتصال بالنموذج إذا فشل تسجيل الحدث الضروري قبله.'],['budget_cli','يتحقق أن عرض الميزانية لا يقرأ .env ولا يستدعي نموذجًا.'],
      ['import','يتحقق أن استيراد الملف لا يبدأ بحثًا أو تحميل .env.'],['cancelled','يتأكد أن إلغاء التأكيد لا يحفظ تقريرًا.'],
      ['backend_parameters','يفحص المهلات وحدود النتائج في استدعاءات الأدوات.'],['plain_text','يفحص استخراج النص من أشكال ردود مختلفة.'],
      ['async','يتأكد من تعطيل مسارات الاتصال غير المعتمدة.'],['suspicious','يرفض إعداد طلب قد يخرج عن حدود التكلفة والأدوات.'],
      ['usage_above','يحفظ الاستهلاك الذي تجاوز التقدير بدل تجاهله.'],['interrupted','يتأكد أن الحجز المتعثر يظل محسوبًا ضمن الحد اليومي.'],
      ['cli_complete','يجرب تشغيل CLI كاملًا ببحث وهمي ثم رفض الحفظ.'],['cli_empty','يتحقق من رفض الإدخال غير الصالح أو المفتاح غير المجهز دون طلب نموذج.'],
      ['recovery','يجرب تعثر مصدر واستخدام مصدر بديل.'],['single_source','يتحقق من ظهور تنبيه عند استخدام مصدر واحد فقط.'],['retry','يفحص أن المحاولات محدودة وحجم الرد مقيد.']
    ];
    return rules.find(([part])=>name.includes(part))?.[1] || 'يفحص حالة محددة من السلوك المسموح باستخدام بيانات وهمية دون تعديل سجل المستخدم الحقيقي.';
  }

  function renderFile(id) {
    const item=file(id);
    if (!item) return intro('صفحة غير موجودة','لم أجد هذا الملف.','اختر ملفًا من القائمة الجانبية.');
    const source=SOURCES[id];
    const index=G.files.indexOf(item);
    const nodes=source?.nodes || [];
    const tests=nodes.filter(node=>node.name.startsWith('test_'));
    return `<div class='eyebrow'>${G.groups[item.group]} / شرح الملف</div><h1 class='file-title'>${esc(item.name)}</h1><div class='facts'><span class='pill'>${esc(item.role)}</span>${source?`<span class='pill gray'>${source.lines} سطرًا • للكود الحالي</span>`:''}${tests.length?`<span class='pill gray'>${tests.length} حالة اختبار</span>`:''}${item.protected?`<span class='pill gold'>محتواه غير مقروء وغير معروض</span>`:''}</div><p class='lead'>${esc(item.intro)}</p>
    ${item.analogy?`<div class='analogy'>${esc(item.analogy)}</div>`:''}
    <section class='section'><h2>متى يعمل؟</h2><p class='muted'>${esc(item.when)}</p></section>
    <div class='io-grid'><div class='io-card'><label>ماذا يأخذ؟</label><p>${esc(item.input)}</p></div><div class='io-card'><label>ماذا يعيد؟</label><p>${esc(item.output)}</p></div></div>
    <section class='section'><div class='section-head'><h2>ماذا يفعل بالضبط؟</h2></div><ol class='step-list'>${item.steps.map(step=>`<li>${esc(step)}</li>`).join('')}</ol></section>
    ${item.example?`<section class='section'>${note('مثال يساعدك على الفهم',esc(item.example))}</section>`:''}
    ${nodes.length?`<section class='section'><div class='section-head'><h2>${tests.length?'أجزاء الملف وحالات اختباره':'أهم الأسماء داخل الملف'}</h2><span class='muted small'>افتح الاسم لتعرف دوره</span></div>${nodes.map(node=>`<details class='fn'><summary><span class='fn-name'>${esc(node.qualified)}</span><small>${node.kind==='class'?'قالب بيانات وعمل':'دالة'} · سطر ${node.line}</small></summary><div class='fn-body'>${esc(functionNote(node))}<br><button class='mini' data-code-line='${node.line}'>شاهد موضعه في الكود ←</button></div></details>`).join('')}</section>`:''}
    <section class='section'>${note('انتبه لهذه النقطة',esc(item.note),true)}</section>
    <section class='section'><h2>ملفات يرتبط بها</h2><div class='chips' style='margin-top:13px'>${item.connections.map(chip).join('')}</div></section>
    ${source?`<section class='section'><details class='source-details' id='source-details'><summary>أريد التوسع: اعرض الكود الحالي لهذا الملف <span class='muted small'>قراءة فقط</span></summary><div class='code-container'><div class='code-head'><span>${esc(item.name)}</span><span>Python • لا يُنفّذ هنا</span></div><div class='code-body' id='source-code'></div></div></details></section>`:''}
    <div class='actions'><button class='btn ${read.has(id)?'secondary':''}' data-mark='${esc(id)}'>${read.has(id)?'✓ فهمت هذا الملف — إلغاء العلامة':'فهمت هذا الملف ✓'}</button><a class='btn secondary' href='#journey'>اربطه برحلة السؤال</a></div>
    <div class='file-pager'>${index>0?`<a class='mini' href='${link(G.files[index-1].id)}'>السابق: <bdi>${esc(G.files[index-1].name)}</bdi></a>`:'<span></span>'}${index<G.files.length-1?`<a class='mini' href='${link(G.files[index+1].id)}'>التالي: <bdi>${esc(G.files[index+1].name)}</bdi> ←</a>`:''}</div>`;
  }

  function renderCode(id) {
    const container=$('#source-code');
    if (!container || container.dataset.ready) return;
    container.innerHTML=SOURCES[id].text.split('\n').map((line,index)=>`<span class='code-line' data-line='${index+1}'><span class='line-no'>${index+1}</span>${esc(line) || ' '}</span>`).join('');
    container.dataset.ready='true';
  }

  function journeySteps() {
    const science=state.mode==='scientific';
    let steps=[
      ['يصل سؤال المستخدم','يقرأ main.py السؤال والنمط. إذا كان السؤال فارغًا أو أطول من الحد المقبول يتوقف قبل تحميل المفتاح أو الاتصال بالنموذج.',['main.py']],
      ['يُجهز فريق البحث',science?'تُتاح أدوات Semantic Scholar وOpenAlex وarXiv والحفظ. لا تُتاح أدوات الويب في هذا النمط.':'تُتاح أدوات DuckDuckGo وWikipedia والحفظ. لا تُتاح الأدوات العلمية في هذا النمط.',['main.py','tools.py']],
      ['المحاسب يراجع الطلب','قبل اتصال النموذج، يفحص budget.py الإعدادات والأدوات وحجم الطلب، ويقارن الحجز المتوقع بميزانية المهمة واليوم والإجمالي.',['budget.py']]
    ];
    if (state.scenario==='budget') return [...steps,['يتوقف قبل الاتصال','في هذا المثال نفترض أن المتبقي لا يكفي. لا يُرسل طلب إلى OpenAI، ويُسجل سبب التوقف. هذا مثال تعليمي، وليس قراءة لرصيدك.',['budget.py','tracing.py']]];
    steps.push(['النموذج يختار أداة',science?'يعيد النموذج اسم أداة علمية واستعلامًا. برنامج Python، لا النموذج نفسه، ينفذ الاتصال بالمصدر.':'يعيد النموذج اسم أداة ويب واستعلامًا. برنامج Python، لا النموذج نفسه، ينفذ الاتصال بالمصدر.',['main.py',science?'scientific_tools.py':'tools.py']]);
    if(state.scenario==='recovery') {
      steps.push([science?'Semantic Scholar يعيد 429':'DuckDuckGo يتعثر',science?'يُسجل التعثر، ثم تُجرب OpenAlex تلقائيًا. لو طُلب الاستعلام نفسه مجددًا تُستخدم النتيجة المؤقتة داخل المهمة.':'يعود خطأ من أداة الويب. يمكن للوكيل اختيار Wikipedia ليكمل بمصدر آخر؛ مشكلة DuckDuckGo نفسها لم تُصلح هنا.',[science?'scientific_tools.py':'tools.py','tracing.py']]);
    }
    steps.push([science?'تُرتب بطاقات الأوراق':'تُجمع الروابط والمقتطفات',science?'تُعاد كلمات الملخص إلى ترتيبها، وتُزال الأوراق المكررة، ولا تُستخدم ورقة بلا ملخص كدليل على نتائجها.':'تُنقح النتائج وتُحفظ الروابط التي رجعت فعليًا. لا يُفتح كل رابط لقراءة صفحة كاملة. ولن يُقبل رابط يختلقه النموذج لاحقًا.',[science?'research_models.py':'tools.py',science?'scientific_tools.py':'safety.py']]);
    steps.push(['تعود الأدلة إلى النموذج','تُرسل نتائج الأدوات إلى النموذج ليكتب الإجابة. إذا احتاج استدعاء آخر تعاد فحوص الميزانية أولًا. «ثلاثة استدعاءات» تعني ثلاث جولات للنموذج، لا ثلاثة مصادر بالضرورة.',['main.py','budget.py']]);
    steps.push(['تُفحص الإجابة',science?'يتحقق البرنامج من الحقول وروابط الأوراق وأرقام المراجع، ثم يضيف أن الإجابة مبنية على الملخصات.':'يتحقق البرنامج من الحقول وروابط المصادر. إذا اعتمدت النتيجة على مصدر واحد يضيف تنبيهًا واضحًا.', ['main.py']]);
    steps.push(['قرار الحفظ بيد المستخدم',state.save==='yes'?'في هذا المثال تختار y. يُحفظ التقرير المتحقق داخل reports باسم جديد بعد فحص الاسم والمسار. النموذج لا يستطيع الموافقة بدلًا عنك.':'في هذا المثال تختار n. تُعرض النتيجة دون كتابة تقرير. قراءة الأدوات لا تمنح موافقة ضمنية على الحفظ.',['tools.py','safety.py']]);
    steps.push(['يُغلق دفتر التنفيذ','تُكتب حالة النهاية وعدد الاستدعاءات والتكلفة والمبالغ التي لم تُسوَّ بعد. دفتر JSONL يصف الأحداث، وusage.json هو مرجع الإنفاق.',['tracing.py','budget.py']]);
    return steps;
  }

  function renderJourney() {
    const steps=journeySteps();
    state.journey=Math.min(state.journey,steps.length-1);
    const current=steps[state.journey];
    return intro('شرح تفاعلي • بلا شبكة أو رصيد','امشِ مع سؤال واحد.','غيّر النمط والحالة، ثم استخدم «الخطوة التالية». كل ما تراه هنا محاكاة تعليمية لا تشغّل كود المشروع.') +
      `<div class='toolbar'><div class='control'><label for='journey-mode'>نمط البحث</label><select id='journey-mode'><option value='web' ${state.mode==='web'?'selected':''}>بحث ويب</option><option value='scientific' ${state.mode==='scientific'?'selected':''}>بحث علمي</option></select></div><div class='control'><label for='journey-scenario'>ماذا يحدث؟</label><select id='journey-scenario'><option value='normal' ${state.scenario==='normal'?'selected':''}>المصدر يعمل</option><option value='recovery' ${state.scenario==='recovery'?'selected':''}>مصدر يتعثر ثم بديل</option><option value='budget' ${state.scenario==='budget'?'selected':''}>الميزانية لا تكفي</option></select></div><div class='control'><label for='journey-save'>قرار الحفظ في المثال</label><select id='journey-save' ${state.scenario==='budget'?'disabled':''}><option value='no' ${state.save==='no'?'selected':''}>أرفض الحفظ</option><option value='yes' ${state.save==='yes'?'selected':''}>أوافق على الحفظ</option></select></div></div>
      <div class='journey-track' aria-label='محطات الرحلة'>${steps.map((_,i)=>`<button aria-label='الانتقال إلى الخطوة ${i+1}' data-step='${i}' class='${i===state.journey?'current':i<state.journey?'done':''}'>${i+1}</button>`).join('')}</div>
      <div class='journey-screen' aria-live='polite'><div class='step-icon'>المحطة ${state.journey+1} من ${steps.length}</div><h2>${current[0]}</h2><p>${current[1]}</p><div class='related-label'>الملفات المسؤولة عن هذه الخطوة</div><div class='chips'>${current[2].map(chip).join('')}</div></div>
      <div class='journey-controls'><button class='btn secondary' data-journey='prev' ${state.journey===0?'disabled':''}>الخطوة السابقة</button><button class='btn' data-journey='next' ${state.journey===steps.length-1?'disabled':''}>الخطوة التالية ←</button></div>
      <section class='section'>${note('تذكر الفرق','الأخطاء هنا سيناريوهات للشرح. لا يُرسل الموقع أي بحث، ولا يكتب تقريرًا، ولا يقرأ سجل ميزانيتك.')}</section>`;
  }

  function renderTerms() {
    return intro('مرجع صغير أثناء القراءة','الكلمات ببساطة.','سترى أسماء إنجليزية في الكود. لا تحتاج حفظها كلها؛ اربط كل اسم بوظيفته هنا.') + `<div class='glossary'>${G.terms.map(([term,text])=>`<article class='term-card'><h3>${esc(term)}</h3><p>${esc(text)}</p></article>`).join('')}</div>`;
  }

  function renderQuiz() {
    return intro('تأكد أنك أمسكت الفكرة','اختبر فهمك بهدوء.','اختر إجابة لتعرف السبب. هذا اختبار تعليمي داخل الصفحة، لا اختبار البرنامج ولا اتصال بالنموذج.') +
      G.quizzes.map((quiz,index)=>`<section class='quiz-card'><span class='eyebrow'>سؤال ${index+1} / ${G.quizzes.length}</span><h3>${quiz.q}</h3><div class='quiz-options'>${quiz.options.map((option,i)=>`<button class='quiz-option ${state.answers[index]!==undefined && i===quiz.answer?'correct':''} ${state.answers[index]===i && i!==quiz.answer?'wrong':''}' data-quiz='${index}' data-answer='${i}'>${option}</button>`).join('')}</div>${state.answers[index]!==undefined?`<p class='quiz-feedback' role='status'>${state.answers[index]===quiz.answer?'✓ صحيح. ':'يمكنك المحاولة مرة أخرى. '}${quiz.why}</p>`:''}</section>`).join('');
  }

  function renderTesting() {
    return intro('من الفهم إلى الاستخدام','كيف أشغّل وأختبر؟','اقرأ وصف كل أمر قبل نسخه. أزرار النسخ تنسخ النص فقط؛ الموقع لا ينفّذ الأوامر.') +
      note('المكان الصحيح','نفّذ الأوامر من مجلد مشروع AI Research Assistant، باستخدام .venv الموجودة. لا تحتاج تنزيل حزم لقراءة هذا الموقع.') +
      `<section class='section'><h2>1. تأكد من سلامة البيئة</h2><p class='muted'>يفحص هذا الأمر أن الحزم المثبتة لا تتعارض في متطلباتها. لا يثبت حزمًا.</p>${command(String.raw`.\.venv\Scripts\python.exe -I -m pip --isolated --disable-pip-version-check check`)}</section>
      <section class='section'><h2>2. اعرض المساعدة والإنفاق</h2><p class='muted'>هذان الأمران لا يقرآن .env ولا يرسلان طلب نموذج.</p>${command(String.raw`.\.venv\Scripts\python.exe -B main.py --help`)}${command(String.raw`.\.venv\Scripts\python.exe -B main.py --budget-status`)}</section>
      <section class='section'><h2>3. شغّل الاختبارات المحلية</h2><p class='muted'>المتوقع ظهور OK. رسائل WARNING في بعض الحالات متعمدة لأن الاختبار يجرب الفشل. في آخر تحقق أثناء تطوير المهمتين 3 و4 اجتاز المشروع 69 اختبارًا.</p>${command(String.raw`.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v`)}<div class='chips'>${['tests/test_task2.py','tests/test_scientific.py','tests/test_tracing_budget.py'].map(chip).join('')}</div></section>
      <section class='section'><h2>4. افحص مصدرًا علميًا دون OpenAI</h2><p class='muted'>يستخدم الإنترنت إلى OpenAlex فقط في هذا المثال، بلا مفاتيح أو رصيد نموذج. يوضح الفرق بين اتصال المصدر واتصال النموذج.</p>${command(String.raw`.\.venv\Scripts\python.exe -B scripts/check_scientific_sources.py --source openalex`)}</section>
      <section class='section'><h2>5. جرّب بحثًا فعليًا عندما تكون جاهزًا</h2><p class='muted'>أعدّ المفتاح محليًا بنفسك، ولا تضعه في المحادثة. هذا الأمر قد يجري عدة استدعاءات للنموذج ضمن حدود التطبيق.</p>${command(String.raw`.\.venv\Scripts\python.exe -B main.py --mode scientific --query "بحث علمي: تطبيقات RAG في التعليم" --verbose`,true)}</section>
      <section class='section'><h2>6. جرّب الحفظ بقرار منك</h2><p class='muted'>عند ظهور التأكيد اكتب y للموافقة أو n للرفض. كل تشغيل جديد للأمر مهمة بحث جديدة قد تستهلك رصيدًا.</p>${command(String.raw`.\.venv\Scripts\python.exe -B main.py --mode scientific --query "بحث علمي: تطبيقات RAG في التعليم" --save scientific_report.txt`,true)}${note('أين يوجد التقرير؟','داخل reports في مجلد المشروع. يعرض البرنامج الاسم الفعلي الذي يضم الوقت والمعرّف. لا تخلط تقاريرك مع reports/.tests الخاصة بالاختبارات.')}</section>
      <section class='section'><h2>كيف أفهم النتيجة؟</h2><div class='table-wrap'><table><thead><tr><th>ما يظهر</th><th>معناه</th></tr></thead><tbody><tr><td>success</td><td>نتيجة اجتازت التحقق دون النقص الذي يغير حالتها.</td></tr><tr><td>degraded</td><td>نتيجة متاحة، مع نقص مصادر أو تعثر معروف.</td></tr><tr><td>rate_limited / 429</td><td>الخدمة لا تسمح بالطلب حاليًا؛ يمكن استخدام بديل مسموح.</td></tr><tr><td>مصادر غير كافية أو غير صالحة</td><td>لن يخترع البرنامج تقريرًا موثقًا من دون أدلة مقبولة.</td></tr><tr><td>حجوزات غير مسوّاة</td><td>مبالغ متوقعة لم تصل بيانات مؤكدة لتسويتها؛ لا تُعتبر مجانية.</td></tr><tr><td>سجل الميزانية تالف أو مفقود</td><td>يتوقف التطبيق لحماية الرصيد؛ لا تصفّره أو تحذفه لإعادة التشغيل.</td></tr></tbody></table></div></section>
      <section class='section'><h2>مثال تعليمي لحساب التكلفة بعد الرد</h2><p class='muted'>الحاسبة تستخدم أسعار الثوابت الموجودة في budget.py وقت إعداد الدليل. ليست قراءة لحسابك أو تسعيرًا حيًا، والحجز قبل الطلب يستخدم تقديرًا أكثر تحفظًا.</p><div class='toolbar'><div class='control'><label for='calc-input'>توكنات إدخال عادية</label><input type='number' id='calc-input' min='0' max='100000' value='2000'></div><div class='control'><label for='calc-output'>توكنات الإخراج</label><input type='number' id='calc-output' min='0' max='1200' value='400'></div></div><div class='budget-results'><div class='metric'><small>المجموع التوضيحي بالدولار</small><b id='calc-total'>$0.00040000</b></div><div class='metric'><small>الطلبات الحقيقية التي أجرتها الصفحة</small><b>0</b></div></div></section>`;
  }

  function renderRoadmap() {
    return intro('افصل التنفيذ عن الخطة','أين وصل المشروع؟','هذا الدليل يصف النسخة الموجودة حتى نهاية المهمتين 3 و4. العناوين المستقبلية ليست ملفات منفّذة.') +
      `<div class='timeline'><article><span class='pill'>منفّذ</span><h3>الأساس والبحث عبر الطرفية</h3><p>استقبال السؤال، واختيار النمط، واستدعاء النموذج، والتحقق من الإجابة، والحفظ المؤكد.</p></article><article><span class='pill'>منفّذ</span><h3>البحث العلمي والميزانية والسجلات</h3><p>ثلاث قواعد علمية، وإزالة التكرار، وملخصات ومراجع، وحدود الإنفاق، وJSONL، واختبارات محلية.</p></article><article><span class='pill gold'>مشكلة معروفة مؤجلة</span><h3>DuckDuckGo</h3><p>ظهر DDGSException في تجربة المستخدم. سبب الخطأ التفصيلي لم يُشخّص بعد. نجاح Wikipedia لا يعني إصلاح هذه المشكلة.</p></article><article class='planned'><span class='pill gold'>خطة المهمة 5 — لم تُنفّذ</span><h3>MCP وذاكرة SQLite</h3><p>خادم حفظ محلي عبر بروتوكول موحد، وذاكرة لنتائج البحث بعد إعادة التشغيل. سجل usage.json الحالي لا يعادل هذه الذاكرة البحثية.</p></article><article class='planned'><span class='pill gold'>خطة المهمة 6 — لم تُنفّذ</span><h3>مراجعة أوسع للصلاحيات والهجمات النصية</h3><p>توحيد السياسة واختبار تعليمات خبيثة تأتي من المصادر والذاكرة وMCP، مع منع العمليات غير المسموحة في التطبيق.</p></article><article class='planned'><span class='pill gray'>مرحلة لاحقة</span><h3>واجهة التطبيق والنشر والتسليم النهائي</h3><p>واجهة Streamlit ورابط تجربة وتحليل تكلفة نهائي. هذا الموقع دليل تعليمي، وليس واجهة Streamlit للمساعد البحثي.</p></article></div>
      ${note('ما الذي ثبت حيًا؟','تجارب المستخدم أثبتت تشغيل النموذج وWikipedia والحفظ. فحص الأدوات العلمية أثبت 429 من Semantic Scholar والتعافي إلى OpenAlex ونجاح arXiv. أما تلخيص علمي كامل من بيئة التطوير وسجلا النجاح والتعافي الكاملان فلم يُستكملا وقت إعداد الدليل.',true)}`;
  }

  function renderAbout() {
    return intro('عن النسخة التعليمية','موقع للقراءة والفهم.','المحتوى مبني على ملفات المشروع الحالية؛ لا يعتمد على افتراض أن كل متطلبات الكابستون مكتملة.') +
      `<div class='card'><h2>كيف صُنع الدليل؟</h2><p class='muted'>قُرئت ملفات الكود المسموحة، ثم كُتب شرح عربي مستقل. جمع build_guide.py قائمة الأسماء وأرقام الأسطر من ملفات Python دون استيرادها أو تنفيذها. لم تُقرأ .env أو sample.env أو مفاتيح أو تقاريرك الخاصة.</p></div>
      <section class='section'><h2>ملفات هذا الموقع نفسه</h2><div class='table-wrap'><table><thead><tr><th>الملف</th><th>وظيفته</th></tr></thead><tbody><tr><td><code>content.js</code></td><td>النص العربي لشرح الملفات والأمثلة والقاموس والأسئلة.</td></tr><tr><td><code>functions.js</code></td><td>شرح مبسط لأسماء الدوال والقوالب البرمجية.</td></tr><tr><td><code>app.js</code></td><td>التنقل والبحث والمحاكاة التعليمية وعرض الكود. لا يستدعي Python.</td></tr><tr><td><code>style.css</code></td><td>الألوان والأحجام وترتيب الصفحة والعرض على الهاتف والطباعة.</td></tr><tr><td><code>build_guide.py</code></td><td>يجمع الشرح والكود الآمن في ملف HTML واحد دون تشغيل التطبيق.</td></tr><tr><td><code>index.html</code></td><td>الموقع النهائي؛ يمكن فتحه محليًا دون تثبيت حزم.</td></tr></tbody></table></div></section>
      <section class='section'>${note('عن علامات «فهمت هذا الملف»','تُحفظ محليًا في متصفحك إن سمح بذلك، وليست في ملفات المشروع أو قاعدة بيانات. لا تعني قراءة ملف سري. وقد لا تستمر في بعض أوضاع المتصفح.')}</section>
      <section class='section'><h2>إعادة فتح الموقع لاحقًا</h2><p class='muted'>serve_guide.py يشغّل خادمًا محليًا يعرض مجلد هذا الدليل فقط، دون استيراد تطبيق البحث. إذا توقف الرابط، شغّل الأمر التالي من مجلد المشروع، ثم افتح http://127.0.0.1:8765/ في لوحة المتصفح. أوقفه بـCtrl+C عندما تنتهي.</p>${command(String.raw`.\.venv\Scripts\python.exe -I -S -B docs/project-guide/serve_guide.py`)}<p class='muted small'>ملف index.html نفسه نسخة مستقلة يمكن فتحها أيضًا في متصفح عادي دون خادم.</p></section>
      <section class='section'><h2>تحديث الدليل بعد تغير الكود</h2><p class='muted'>إذا تغير البرنامج لاحقًا، يلزم تحديث الشرح عند تغير المعنى، ثم إعادة بناء النسخة المجمعة. الأمر التالي محلي ولا يقرأ الأسرار ولا يجري بحثًا:</p>${command(String.raw`.\.venv\Scripts\python.exe -I -S -B docs/project-guide/build_guide.py`)}</section>`;
  }

  function render(keepScroll=false) {
    const y=window.scrollY;
    const route=state.route;
    const fileId=route.startsWith('file/')?route.slice(5):null;
    const renderer={home:renderHome,map:renderMap,journey:renderJourney,terms:renderTerms,quiz:renderQuiz,testing:renderTesting,roadmap:renderRoadmap,about:renderAbout}[route];
    $('#article').innerHTML=fileId?renderFile(fileId):(renderer || renderHome)();
    const title=fileId?(file(fileId)?.name || 'ملف'):pages.find(([id])=>id===route)?.[1] || 'ابدأ من هنا';
    $('#breadcrumb').textContent='دليل المساعد البحثي / '+title;
    document.title=title+' | افهم مشروعك';
    renderNav();
    if (fileId && $('#source-details')) $('#source-details').addEventListener('toggle',()=>{if($('#source-details').open)renderCode(fileId);});
    if (!keepScroll) window.scrollTo({top:0,behavior:'instant'}); else window.scrollTo({top:y,behavior:'instant'});
  }

  function sidebarAccess() {
    const hidden=innerWidth<781 && !$('#sidebar').classList.contains('open');
    $('#sidebar').inert=hidden;
    $('#sidebar').setAttribute('aria-hidden',String(hidden));
  }
  function closeMenu() { $('#sidebar').classList.remove('open'); $('#overlay').classList.remove('open'); $('#menu-toggle').setAttribute('aria-expanded','false'); sidebarAccess(); }
  function routeFromHash() {
    try {state.route=decodeURIComponent(location.hash.slice(1)) || 'home';} catch(_){state.route='home';}
    closeMenu(); render();
  }

  document.addEventListener('click',async event=>{
    const target=event.target.closest('button,a'); if(!target)return;
    if(target.id==='menu-toggle'){const open=$('#sidebar').classList.toggle('open');$('#overlay').classList.toggle('open',open);target.setAttribute('aria-expanded',String(open));sidebarAccess();}
    if(target.id==='print-page')window.print();
    if(target.dataset.mark){const id=target.dataset.mark;read.has(id)?read.delete(id):read.add(id);try{localStorage.setItem('research-guide-read-v1',JSON.stringify([...read]));}catch(_){}target.textContent=read.has(id)?'✓ فهمت هذا الملف — إلغاء العلامة':'فهمت هذا الملف ✓';target.classList.toggle('secondary',read.has(id));renderNav();}
    if(target.dataset.journey){state.journey+=target.dataset.journey==='next'?1:-1;render(true);}
    if(target.dataset.step!==undefined){state.journey=Number(target.dataset.step);render(true);}
    if(target.dataset.quiz!==undefined){state.answers[target.dataset.quiz]=Number(target.dataset.answer);render(true);}
    if(target.dataset.codeLine){const details=$('#source-details');if(details){details.open=true;renderCode(state.route.slice(5));document.querySelectorAll('.code-line.highlight').forEach(line=>line.classList.remove('highlight'));const line=$(`[data-line='${target.dataset.codeLine}']`);line?.classList.add('highlight');line?.scrollIntoView({behavior:'smooth',block:'center'});}}
    if(target.dataset.copy){try{if(!navigator.clipboard?.writeText)throw new Error('unavailable');await navigator.clipboard.writeText(target.dataset.copy);target.textContent='نُسخ ✓';}catch(_){const code=target.previousElementSibling;const selection=window.getSelection();const range=document.createRange();range.selectNodeContents(code);selection.removeAllRanges();selection.addRange(range);target.textContent='حددته لك — انسخه';}}
  });
  document.addEventListener('change',event=>{const id=event.target.id;if(id.startsWith('journey-')){state[{ 'journey-mode':'mode','journey-scenario':'scenario','journey-save':'save'}[id]]=event.target.value;state.journey=0;render(true);}});
  document.addEventListener('input',event=>{if(event.target.id==='nav-search'){state.search=event.target.value;renderNav();}if(event.target.id.startsWith('calc-')){const input=Math.max(0,Math.min(100000,Number($('#calc-input').value)||0));const output=Math.max(0,Math.min(1200,Number($('#calc-output').value)||0));$('#calc-total').textContent='$'+(input*.1/1000000+output*.5/1000000).toFixed(8);}});
  document.addEventListener('keydown',event=>{if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='k'){event.preventDefault();if(innerWidth<781){$('#sidebar').classList.add('open');$('#overlay').classList.add('open');$('#menu-toggle').setAttribute('aria-expanded','true');}sidebarAccess();$('#nav-search').focus();}if(event.key==='Escape'){closeMenu();$('#nav-search').value='';state.search='';renderNav();}});
  $('#overlay').addEventListener('click',closeMenu);
  window.addEventListener('hashchange',routeFromHash);
  window.addEventListener('resize',()=>{if(innerWidth>=781)closeMenu();else sidebarAccess();});
  routeFromHash();
})();
