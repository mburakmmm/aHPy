# aHPy production yol haritası

Bu dosya, aHPy'yi kontrollü alpha seviyesinden güvenilir bir production
sürümüne taşımak için kalan işleri bağımlılık sırasıyla toplar.

`TODO.md` ayrıntılı ve normatif proje kapsamıdır. `AGENTTODO.md` agent handoff
kuyruğudur. Bu dosya ise yalnızca production/release hedefinin yürütme
listesidir. Bir madde burada tamamlandığında ilgili `TODO.md`, destek matrisi,
validasyon matrisi, audit ve değişiklik kaydı da aynı commit içinde
güncellenmelidir.

## Yeni ana hedef

> aHPy'nin ilan edilen destek sözleşmesi içinde doğrudan Universal HPy kodu
> üreten, sessiz fallback yapmayan, kaynak ve binary sınırları doğrulanmış,
> yeniden üretilebilir artifact'leri bulunan ve gerçek kütüphanelerle
> kanıtlanmış ilk production sürümünü yayımlamak.

Bu hedef yalnızca kodun derlenmesiyle tamamlanmış sayılmaz. Aynı release
candidate üzerinde correctness, ownership, portability, packaging,
performance, documentation, security ve bakım kapılarının tamamı kapanmalıdır.

### Durum anahtarı

- `[x]`: Kanıtı kaydedilmiş ve tamamlanmış iş.
- `[ ]`: Yapılacak veya hosted kanıtı henüz tamamlanmamış iş.
- **AKTİF**: Şu anda üzerinde çalışılan ve bir sonraki commit'i belirleyen faz.
- **SIRADAKİ**: Aktif faz kapanınca başlanacak faz.
- **BEKLİYOR**: Önceki fazların çıkış kapısına bağımlı faz.
- **DIŞ BAĞIMLILIK**: Sonuç için upstream proje, servis veya maintainer kararı
  gereken iş; yine de reproducer, issue ve kapsam kararı aHPy sorumluluğundadır.

### Faz panosu

| Sıra | Faz | Durum | Production sonucuna katkısı |
| ---: | --- | --- | --- |
| 0 | PRD-0 — Mevcut dalı yeşile getir | **TAMAMLANDI** | Güvenilir aynı-HEAD CI tabanı |
| 1 | PRD-1 — Destek sözleşmesini dondur | **AKTİF** | İlk sürümün dürüst kapsamı |
| 2 | PRD-2 — Core compiler/module state | **SIRADAKİ** | Ownership ve semantic correctness |
| 3 | PRD-3 — Pure HPy extension type | **BEKLİYOR** | Type/GC/finalizer güvenliği |
| 4 | PRD-4 — Advanced Cython aileleri | **BEKLİYOR** | Implement veya fail-closed sonucu |
| 5 | PRD-5 — Portability/native memory | **BEKLİYOR** | Universal binary ve platform kanıtı |
| 6 | PRD-6 — Paketleme/dağıtım | **BEKLİYOR** | Kurulabilir ve doğrulanabilir artifact |
| 7 | PRD-7 — Performans/footprint | **BEKLİYOR** | Sürüm bütçeleri ve regresyon kapısı |
| 8 | PRD-8 — Gerçek kütüphane pilotları | **BEKLİYOR** | Kullanıcı dünyasında çalışma kanıtı |
| 9 | PRD-9 — Upstream/güvenlik/bakım | **BEKLİYOR** | Sürdürülebilir production işletimi |
| 10 | PRD-10 — RC/stable yayın | **BEKLİYOR** | İmzalı ve kanıtlı production release |

### Şu anki kritik yol

1. Final kanıt commit'inin required context'lerini yeniden yeşil doğrula ve
   final run/job bağlantılarını commit döngüsü yaratmadan PR açıklamasında tut.
2. PRD-1 için ilk sürümün ürün seviyesini ve exact Cython tabanını belirle.
3. HPy, Python, OS/compiler ve build frontend destek sözleşmelerini dondur.
4. “Supported”, “partial”, “blocked” ve “rejected” terimlerini kullanıcı
   açısından normatif biçimde tanımla.
5. README, support/validation matrisleri, onboarding ve release politikasını
   tek destek sözleşmesine eşitle.

## Başlangıç durumu

- Başlangıç tarihi: 2026-07-28.
- Başlangıç commit'i: `0924dc88049a514382b2befaae7b70074645f25b`.
- PRD-0 CI uygulama commit'i: `e791c8983bcb1a3c38aa932617a91ea976cb5c55`.
- Çalışma dalı: `codex/ahpy-bootstrap`.
- Release dalı değildir; release politikası gereği production hattı daha sonra
  `ahpy/<cython-major>.<cython-minor>` biçiminde açılacaktır.
- Stabil yerel ortam: CPython 3.11.15 + HPy 0.9.0.
- Mevcut odaklı doğrulama: 431 compiler/seam testi, 153 quality-tool testi ve
  iki yorumlayıcıda 584 coverage testi.
- Universal backend Python modülleri için ölçülen satır kapsamı: %100.
- Bu oran generated C, native runtime, binary portability veya bütün Cython
  özelliklerinin %100 desteklendiği anlamına gelmez.
- Mevcut uygun sınıflandırma: production-grade prototype / alpha.

## Her fazda korunan production kuralları

- Universal mod hiçbir zaman CPython, Limited API veya HPy Hybrid moduna
  sessizce düşmemeli.
- Generated Universal kaynakta `Python.h`, `PyObject *`, `cpython.*` veya
  yasaklı CPython sembolü bulunmamalı.
- Desteklenmeyen her kaynak yapısı, doğru kaynak konumunda uygulanabilir
  bir diagnostic ile durmalı; traceback veya internal compiler error
  üretmemeli.
- HPy 0.9 public API'sinde bulunmayan özellikler private API, CPython slotu
  veya yaklaşık davranışla taklit edilmemeli.
- Her yeni executable davranış normal, HPy Trace ve HPy Debug modlarında
  sınanmalı.
- Her ownership değişikliği başarı, ara API hatası, erken çıkış ve cleanup
  yollarını kapsamalı.
- Frontend değişiklikleri CPython C ve C++ semantic oracle'larını
  çalıştırmalı.
- Kullanıcıya ait veya kapsam dışı çalışma ağacı dosyaları stage
  edilmemeli.
- Hosted evidence görülmeden bir platform, yorumlayıcı veya özellik
  “supported” olarak işaretlenmemeli.

## PRD-0 — Mevcut dalı tamamen yeşile getir

Bu kapı kapanmadan yeni production özelliği eklenmez.

- [x] Son commit için devam eden bütün GitHub Actions işlerinin bitmesini
      bekle ve sonuçları kaydet.
- [x] `Benchmarks` workflow'undaki `benchmark_results_*.csv` bulunamadığı için
      kırılan summary adımının local düzeltmesini hosted yeşil koşuyla doğrula.
  - [x] Benchmark üretilmeyen bir değişiklikte summary adımı güvenli biçimde
        skip etmeli.
  - [x] Benchmark beklenen koşuda eksik artifact fail-closed davranmalı.
  - [x] Her iki davranış için workflow/quality regresyon testi ekle.
- [x] Push ve pull-request eventlerinden gelen mükerrer pahalı workflow
      koşularını incele; gerekli değilse concurrency/dedup politikası ekle.
- [x] Mandatory, allowed-failure, schedule-only ve manual-only işlerin listesini
      tek kaynakta tanımla ve test et.
- [x] `main` ve gelecekteki `ahpy/**` release dalları için GitHub
      branch-protection/ruleset politikasını uygula:
  - [x] Değişikliklerin pull request üzerinden gelmesini zorunlu kıl.
  - [x] `tests/ahpy/ci-policy.toml` içindeki zorunlu PR kontrollerini gerçek
        required status check bağlamlarına eşle.
  - [x] Allowed-failure, schedule-only, manual-only ve release-only işlerini
        required PR check listesine katma.
  - [x] Force-push ve dal silmeyi engelle; maintainer bypass politikasını
        belgeye bağla.
  - [x] Ruleset ayarını GitHub API çıktısıyla audit belgesinde kanıtla.
- [x] Mandatory işlerde `pending`, `cancelled` veya `failure` kalmadığını
      doğrula.
  - [x] `aHPy required checks` — run `30361153504`, job `90283757405`.
  - [x] `benchmark required checks` — run `30361153497`, job `90296401321`.
  - [x] `ci-success` — run `30361153866`, job `90328870116`.
  - [x] `coverage required checks` — run `30361153526`, job `90291908521`.
  - [x] `sanitizers-success` — run `30361153809`, job `90296760091`.
- [x] Allowed-failure sonuçlarının aggregate required check'i yanlışlıkla
      kırmadığını doğrula.
- [x] Son yeşil run kimliklerini `validation-matrix.md`, ilgili M8 audit'i,
      `AGENTTODO.md` ve PR açıklamasına işle.

### PRD-0 çıkış kapısı

- [x] Aynı HEAD üzerinde clean-build mandatory CI tamamen yeşil.
- [x] Kırmızı kalan her iş açıkça allowed-failure ve destek iddiası dışında.
- [x] README ve kanıt belgeleri aynı commit/run durumunu gösteriyor.

## PRD-1 — İlk production sürümünün destek sözleşmesini dondur

- [ ] İlk sürümün ürün seviyesini seç: `preview`, `beta`, `release candidate`
      veya `stable`.
- [ ] İlk sürümün exact Cython base commit ve sürümünü belirle.
- [ ] Desteklenen HPy sürümlerini tam commit/sürüm olarak belirle.
- [ ] Desteklenen Python yorumlayıcı ve sürümlerini belirle.
- [ ] Desteklenen OS/compiler matrisini belirle.
- [ ] Desteklenen build frontendlerini belirle:
  - [ ] Doğrudan build.
  - [ ] setuptools/cythonize.
  - [ ] PEP 517.
  - [ ] CMake.
  - [ ] Meson.
  - [ ] scikit-build-core.
- [ ] “Supported”, “partial”, “blocked” ve “rejected” terimlerini release
      notlarında kullanıcı açısından tanımla.
- [ ] General Cython compatibility iddiası yapılmayacağını açıkça yaz.
- [ ] PyPy/GraalPy aynı-binary desteği sağlanamazsa ilk sürümün Universal
      iddiasını daralt veya stable etiketi kullanma.
- [ ] HPy 0.9 dış API engellerini ayrı bir known-limitations belgesinde kilitle.
- [ ] Destek sözleşmesini `support-matrix.md`, `validation-matrix.md`, README,
      onboarding ve release policy ile eşitle.

### PRD-1 çıkış kapısı

- [ ] Her kullanıcı özelliği tek bir support status'a sahip.
- [ ] Her support status'ın testi, diagnostic'i veya dış engel kanıtı bağlı.
- [ ] Release kapsamının dışında kalan hiçbir özellik dolaylı biçimde
      production iddiasına dahil edilmiyor.

## PRD-2 — Core compiler, ownership ve module-state kapılarını kapat

- [ ] M2'de kalan her `return`, `break`, `continue`, `goto` ve exception
      çıkışında ownership/cleanup propagation'ı tamamla.
- [ ] Python ile etkileşen kalan utility yollarına context propagation ekle;
      kanıtlanmış pure-C helper'ları context-free tut.
- [ ] Her kalan ara HPy allocation/API çağrısından sonra kontrollü hata
      enjeksiyonu ekle.
- [ ] Borrowed, owned, moved, closed, field, global ve context-constant
      handle durumlarının tamamını model/test et.
- [ ] M3'te release kapsamına alınan module-function imzaları, container/call,
      control-flow, import/global/default ve exception ailelerinin parent
      maddelerini kapat.
- [ ] M4'te release kapsamındaki bütün güvenli cache'leri interpreter-owned
      storage'a taşı.
- [ ] Mutable Python state'in kayıt dışı C globalinde tutulmadığını kaynak ve
      davranış testleriyle doğrula.
- [ ] Failed import, reload, teardown, concurrent import ve subinterpreter
      yollarını release kapsamı için tekrar çalıştır.
- [ ] Generated source ve binary forbidden-symbol audit'lerini bütün maintained
      corpus üzerinde çalıştır.
- [ ] Tam CPython C/C++ regression matrisini current release base üzerinde
      çalıştır ve farkları incele.

### PRD-2 çıkış kapısı

- [ ] Release kapsamındaki core compiler özellikleri için açık ownership veya
      cleanup TODO'su kalmadı.
- [ ] Normal/Trace/Debug, fault injection ve CPython regresyonları yeşil.
- [ ] Bilinen leak, invalid handle, double-close veya borrowed-handle close
      hatası sıfır.

## PRD-3 — Pure HPy extension type kapısını kapat

- [ ] M5 method/member/getset/slot parent maddesini release kapsamı için kapat.
- [ ] Native member storage ve direct method access matrisindeki kalan türleri
      tamamla veya exact diagnostic ile sınır dışına al.
- [ ] Constructor, `__cinit__`, `__init__`, allocation ve partial-object
      cleanup matrisini tamamla.
- [ ] GC traversal, clear, finalization ve resurrection stresini bütün
      desteklenen yorumlayıcı şeritlerinde çalıştır.
- [ ] Weakref, portable instance `__dict__`, context-bearing `__dealloc__` ve
      freelist politikasını HPy sürümüne göre kesin olarak destekle, engelle
      veya reddet.
- [ ] Fused extension type politikasını ayrı olarak belirle.
- [ ] Multiple inheritance için implement/reject kararını exact diagnostic ile
      kapat.
- [ ] Forward-declared, cross-module generated, builtin base ve metaclass
      senaryolarını ayrı ayrı implement/reject et.
- [ ] Variable-size layout'ların fail-closed kaldığını doğrula.
- [ ] Release kapsamındaki bütün special method ve numeric/sequence/mapping
      slotlarını semantic, inheritance ve failure-path testleriyle kapat.
- [ ] Type, field, descriptor ve finalizer durumunu en az üç subinterpreter
      altında doğrula.

### PRD-3 çıkış kapısı

- [ ] Extension-type suite bütün desteklenen yorumlayıcı/platformlarda yeşil.
- [ ] Traverse/clear/finalize/cyclic-GC Debug testleri temiz.
- [ ] Kapsam dışındaki her type özelliği source-located diagnostic üretiyor.

## PRD-4 — Advanced Cython ailelerini tek tek sonuçlandır

Her aile için yalnızca iki kabul edilebilir sonuç vardır:

1. Ownership/context tasarımı, implementation, normal/Trace/Debug testleri ve
   destek kanıtıyla enabled.
2. Sürüm belirtilen diagnostic, test ve migration guidance ile
   blocked/rejected.

- [ ] Generic iterator protokolü ve pure-type `__iter__`/`__next__`.
- [ ] Generator, `yield`, `yield from`, `send`, `throw` ve `close`.
- [ ] Native coroutine, `async`/`await` ve async generator.
- [ ] Buffer producer acquisition/release ownership modeli.
- [ ] Buffer consumer ve typed memoryview.
- [ ] Fused types ve specialization dispatcher.
- [ ] Genel `nogil`, execution re-entry ve exception reacquisition.
- [ ] `prange`, OpenMP, synchronization ve free-threading.
- [ ] Python state taşıyan C callback'leri.
- [ ] Capsules ve cross-module public/C API.
- [ ] C++ compilation, exception translation, STL ve RAII cleanup.
- [ ] Profiling, tracing, coverage, monitoring ve traceback üretimi.
- [ ] Pickling, signatures, annotations, code object ve introspection.
- [ ] Embedding ve birden fazla embedded HPy module.
- [ ] NumPy ve diğer CPython-only third-party C API politikası.
- [ ] Set construction/mutation HPy public API eksikliği.
- [ ] Genel exception state: `except as`, bare reraise, traceback, cause,
      chaining, `else`, `finally` ve nested handlers.
- [ ] HPy method function-object/`__defaults__`/code-object introspection
      eksikleri.

### PRD-4 çıkış kapısı

- [ ] Hiçbir advanced aile belirsiz veya yarım enabled durumda değil.
- [ ] Release kapsamındaki aileler tam testli; diğerleri deterministik ve
      belgelenmiş şekilde fail-closed.

## PRD-5 — Universal portability ve native-memory kanıtını tamamla

- [ ] Aynı hash'e sahip `.hpy0` binary'yi desteklenen bütün yorumlayıcılarda
      çalıştır.
- [ ] PyPy HPy bridge/import problemini upstream durumuyla birlikte çöz veya
      destek kapsamından çıkar.
- [ ] GraalPy HPy bridge/native `.hpy0` import-hook problemini çöz veya destek
      kapsamından çıkar.
- [ ] Aynı binary için normal, Trace ve Debug semantiğini karşılaştır.
- [ ] Stable HPy 0.9 şeridini bütün desteklenen platformlarda tekrar doğrula.
- [ ] Pinned HPy development şeridini Python 3.11 üzerinde doğrula.
- [ ] Python 3.14 + HPy development `SIGSEGV` durumunu minimal reproducer ile
      sınıflandır; dış sorun ise upstream'e bildir ve allowed-failure tut.
- [ ] CPython prerelease + HPy stable nightly sonucunu izlemeye devam et;
      nightly sonucu stable destek iddiasına dönüştürme.
- [ ] Linux Valgrind/LSan positive control ve gerçek corpus kapısını release
      run'ında çalıştır.
- [ ] Windows AppVerifier/full-page-heap artifact'ını incele, injection ve
      positive-control kanıtından sonra kapıyı promote et.
- [ ] ASan ve UBSan'ı bütün desteklenen native derleyici ailelerinde çalıştır.
- [ ] Uygulanabilen platformlarda TSan/free-threading politikasını belirle.
- [ ] Portability artifact hash, binary imports ve source boundary raporlarını
      release provenance'a ekle.

### PRD-5 çıkış kapısı

- [ ] İlan edilen cross-interpreter matrisinde aynı binary yeşil.
- [ ] Bütün zorunlu platform/compiler/sanitizer işleri clean build'den yeşil.
- [ ] Native-memory positive control'leri gerçek kapıların çalıştığını
      kanıtlıyor.

## PRD-6 — Paketleme ve dağıtım hattını production seviyesine getir

- [ ] `aHPy-compiler` dağıtım adını proje sahibi hesabında ayır.
- [ ] Version metadata'ya exact Cython base, aHPy commit ve HPy compatibility
      bilgisini ekle/doğrula.
- [ ] Clean source tree'den sdist ve frontend wheel üret.
- [ ] Sdist/wheel member safety, completeness ve license/provenance audit'ini
      çalıştır.
- [ ] İki bağımsız clean root'ta byte-reproducible frontend artifact üret.
- [ ] Fresh venv içinde no-index install/uninstall/reinstall testi çalıştır.
- [ ] PEP 517'in yanlışlıkla upstream Cython veya başka `ahpy` paketini
      çözümlemediğini doğrula.
- [ ] Direct build, setuptools, CMake, Meson ve scikit-build-core
      dokümantasyonlarını temiz ortamda yeniden çalıştır.
- [ ] CMake/Meson/scikit-build Windows ve cross-build kapsamını tamamla veya
      açıkça sınırla.
- [ ] HPy/PyPA standart Universal wheel/tag sözleşmesini seçmeden özel tag
      üretme veya CPython-tagged wheel'i Universal olarak adlandırma.
- [ ] Universal wheel standardı hazır değilse `.hpy0` portability artifact
      dağıtım yolunu açıkça tanımla ve stable release kapsamını buna göre
      sınırla.
- [ ] Standardize Universal wheel mevcut olduğunda onun reproducibility,
      install ve cross-interpreter testlerini ekle.
- [ ] Artifact checksum, SBOM, license listesi ve build provenance üret.
- [ ] Release artifact'lerini imzala ve doğrulama talimatını yayımla.
- [ ] PyPI/TestPyPI yayınlama ve geri çekme/yeniden yayınlamama politikasını
      belgeleyip dry-run yap.

### PRD-6 çıkış kapısı

- [ ] Yeni kullanıcı checkout bağımlılığı olmadan ilan edilen yolu kurup
      örneği build/import edebiliyor.
- [ ] Artifact kimliği, kaynağı, hash'i ve destek kapsamı doğrulanabiliyor.
- [ ] Dağıtım metadata'sı Universal destek konusunda yanıltıcı değil.

## PRD-7 — Release performans ve footprint bütçelerini sabitle

- [ ] Benchmark workflow artifact/summary hatasını PRD-0 kapsamında kapat.
- [ ] Generated Universal ve eşdeğer handwritten HPy implementasyonlarını bütün
      release benchmark ailelerinde tut.
- [ ] Classic Cython, HPy CPython ABI ve HPy Universal ABI sonuçlarını ayrı
      raporla.
- [ ] Calls, arithmetic, containers, attributes, exceptions, types ve
      external-C için hosted history biriktir.
- [ ] Release kapsamında destekleniyorsa iteration ve memoryview benchmark'ı
      ekle; desteklenmiyorsa “blocked/non-comparable” olarak bırak.
- [ ] Compile time, C compiler time, generated C boyutu, binary boyutu ve peak
      memory ölç.
- [ ] Gürültü analiziyle mutlak/nispi release eşiklerini versiyonla.
- [ ] Eşik aşımında fail-closed CI ve anlamlı rapor üret.
- [ ] HPy runtime/interpreter maliyetini aHPy overhead'inden ayrı göster.
- [ ] Ownership kanıtı olmadan Dup/Close optimizasyonu yapma.

### PRD-7 çıkış kapısı

- [ ] Bütün yayımlanan bütçeler aynı release candidate üzerinde yeşil.
- [ ] Sonuçlar timestamped, immutable CI artifact olarak saklanıyor.
- [ ] Desteklenmeyen aileler için uydurma performans sayısı yayımlanmıyor.

## PRD-8 — Gerçek kütüphane pilotlarını tamamla

- [ ] Doğrudan Python C API kullanmayan saf Cython pilotunu seç.
- [ ] Python-independent C kütüphanesini saran pilotu seç.
- [ ] Extension type, GC ve inheritance kullanan pilotu seç.
- [ ] CPython/NumPy C API nedeniyle bilerek blocked olacak pilotu seç.
- [ ] Her pilot için upstream sürüm/commit ve lisans kaydı tut.
- [ ] Her pilot için gereken kaynak değişikliklerini kaydet.
- [ ] Her pilotun build, test, normal/Trace/Debug ve performance sonuçlarını
      kaydet.
- [ ] Ortak portlama değişikliklerini backend desteğine veya migration
      kuralına dönüştür.
- [ ] Blocked pilotun source-located diagnostics kalitesini doğrula.
- [ ] CI artifact'lerinden compatibility dashboard üret.
- [ ] Library-author porting guide yayımla.
- [ ] Bug/compatibility issue template ekle.
- [ ] HPy conformance corpus'unu kullanıcının programlama diliyle paylaşırken
      Cython frontend internallerine bağımlılık oluşturma.

### PRD-8 çıkış kapısı

- [ ] Dört pilotun raporu ve yeniden çalıştırılabilir CI kanıtı yayımlandı.
- [ ] En az bir gerçek üçüncü taraf proje ilan edilen production yolunda
      source/binary/Debug kapılarını geçiyor.

## PRD-9 — Upstream, güvenlik ve sürdürülebilir bakım

- [ ] Cython maintainer'larıyla backend-neutral seam tasarımını görüş.
- [ ] Backend-neutral refactor'ları küçük bağımsız upstream PR'larına ayır.
- [ ] HPy API eksiklerini minimal reproducer ile upstream issue/PR olarak aç.
- [ ] PyPy/GraalPy bridge sorunlarını ilgili upstream projelere taşı.
- [ ] Cython upstream rebase log'unu ve conflict kararlarını güncel tut.
- [ ] Release branch/backport politikasını uygula.
- [ ] Security policy ve özel vulnerability reporting kanalını yayımla.
- [ ] Desteklenen Cython, HPy, Python, OS ve compiler sürüm politikasını yayımla.
- [ ] Dependency update ve security scanning otomasyonunu ekle.
- [ ] Third-party license/provenance envanterini release artifact'e bağla.
- [ ] User, contributor, architecture, debugging ve release belgelerini
      tamamla.
- [ ] Deprecation, compatibility-break ve migration politikasını tanımla.
- [ ] Periyodik Cython/HPy/interpreter/compiler/platform update cadence'i
      tanımla.
- [ ] Maintainer ownership, issue triage ve release sorumlularını belirle.

### PRD-9 çıkış kapısı

- [ ] Açık upstream bağımlılıkları issue/reproducer bağlantısına sahip.
- [ ] Güvenlik bildirimi, destek süresi ve bakım sorumluluğu kullanıcı için
      açık.
- [ ] Fork güncelleme ve release üretme süreci tek kişilik örtük bilgiye
      bağlı değil.

## PRD-10 — Release candidate ve stable yayın

- [ ] Production kapsamındaki bütün önceki PRD kapılarını kapat.
- [ ] Exact Cython base üzerinden `ahpy/<cython-major>.<cython-minor>` release
      dalını oluştur.
- [ ] PEP 440 uyumlu release candidate sürümünü belirle.
- [ ] Changelog ve release notes'a şunları ekle:
  - [ ] Exact Cython base ve aHPy commit.
  - [ ] HPy sürümleri.
  - [ ] Interpreter/OS/compiler matrisi.
  - [ ] Supported/partial/blocked/rejected özellikler.
  - [ ] Bilinen dış HPy/packaging engelleri.
  - [ ] Performance ve footprint sonuçları.
  - [ ] Artifact provenance ve doğrulama adımları.
- [ ] Release candidate artifact'lerini tamamen clean ortamda üret.
- [ ] Bütün mandatory CI matrisini release candidate artifact'leriyle çalıştır.
- [ ] Aynı `.hpy0` artifact hash'ini ilan edilen yorumlayıcılarda doğrula.
- [ ] Fresh-user onboarding testini yayınlanan artifact üzerinden çalıştır.
- [ ] İki ardışık clean release-candidate koşusunda aynı zorunlu kapıları
      yeşil gör.
- [ ] Kullanıcı pilotlarından release candidate geri bildirimi topla.
- [ ] Kritik ve yüksek öncelikli açık defect bırakma.
- [ ] Geri çekme, security fix ve backport prosedürünü dry-run et.
- [ ] Stable sürümü yalnızca bütün aşağıdaki definition-of-done maddeleri
      tamamlandığında tag'le.

## Production definition of done

- [ ] İlan edilen support tier'ların bütün işleri tamamlandı.
- [ ] Aynı HEAD/release candidate üzerinde bütün mandatory CI işleri yeşil.
- [ ] HPy Debug Mode backend kaynaklı handle hatası göstermiyor.
- [ ] Universal source/binary yasaklı CPython bağımlılığı içermiyor.
- [ ] Aynı Universal binary ilan edilen cross-interpreter matrisini geçiyor.
- [ ] CPython backend regresyonu yok veya upstream tarafından açıkça kabul
      edilmiş.
- [ ] Release performance ve footprint bütçeleri yeşil.
- [ ] Source ve binary artifact'ler yeniden üretilebilir ve provenance
      doğrulanabilir.
- [ ] Paket metadata'sı gerçek portability kapsamını doğru söylüyor.
- [ ] Documentation, diagnostics, examples, migration tooling ve pilot
      raporları gerçek davranışla eşleşiyor.
- [ ] Ertelenen her özellik açıkça partial, blocked veya rejected.
- [ ] HPy 0.9 hard gap'leri private/CPython emülasyonu olmadan fail-closed.
- [ ] Security, vulnerability reporting, supported-version ve maintenance
      politikaları yayımlanmış.
- [ ] M10 pilotları ve compatibility dashboard yayımlanmış.
- [ ] M11 upstream/release/maintenance sorumlulukları tamamlanmış.
- [ ] Release candidate matrisi temiz ve stable tag maintainer onayı almış.

## Her iş maddesi için tamamlama protokolü

Bir checkbox ancak aşağıdaki zincirin tamamı gerçekleştiğinde `[x]` yapılır:

1. Davranış ve kapsam kararı ilgili ADR/support matrix içinde açık.
2. Implementation veya bilinçli fail-closed diagnostic tamam.
3. Başarı, hata, erken çıkış ve cleanup yolları için odaklı regresyonlar yeşil.
4. Uygulanabilir her executable örnek normal, Trace ve Debug modlarında yeşil.
5. Generated source, binary symbol ve ownership sınırları audit edilmiş.
6. CPython frontend etkileniyorsa C ve C++ semantic oracle'ları yeşil.
7. Kullanıcı belgesi, `TODO.md`, `AGENTTODO.md`, validation matrix, milestone
   audit'i ve changelog aynı gerçek durumu gösteriyor.
8. İlgili değişiklik kasıtlı bir commit olarak push edilmiş.
9. Hosted mandatory kontroller aynı HEAD üzerinde yeşil ve run/job bağlantıları
   kanıt belgelerine kaydedilmiş.
10. Çalışma ağacındaki kullanıcıya ait veya ilgisiz dosyalar commit'e
    alınmamış.

## Uygulama sırası

Agent'lar ve geliştiriciler aşağıdaki sırayı korumalıdır:

1. PRD-0: mevcut CI kırmızılarını ve pending kanıtı kapat.
2. PRD-1: ilk release'in gerçek destek kapsamını dondur.
3. PRD-2 ve PRD-3: core compiler ile extension-type correctness kapıları.
4. PRD-4: her advanced aileyi implement veya fail-closed olarak sonuçlandır.
5. PRD-5: cross-interpreter/platform/native-memory kanıtı.
6. PRD-6: dağıtım, artifact kimliği ve provenance.
7. PRD-7: hosted release performans bütçeleri.
8. PRD-8: dört gerçek kütüphane pilotu.
9. PRD-9: upstream, güvenlik ve bakım.
10. PRD-10: release candidate ve stable yayın.

Bir sonraki aktif hedef PRD-1 destek sözleşmesidir.
