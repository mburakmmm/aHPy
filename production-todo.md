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
| 1 | PRD-1 — Destek sözleşmesini dondur | **TAMAMLANDI** | İlk sürümün dürüst kapsamı |
| 2 | PRD-2 — Core compiler/module state | **TAMAMLANDI** | Ownership ve semantic correctness |
| 3 | PRD-3 — Pure HPy extension type | **TAMAMLANDI** | Type/GC/finalizer güvenliği |
| 4 | PRD-4 — Advanced Cython aileleri | **TAMAMLANDI** | Implement veya fail-closed sonucu |
| 5 | PRD-5 — Portability/native memory | **DIŞ BAĞIMLILIK** | Universal binary ve platform kanıtı |
| 6 | PRD-6 — Paketleme/dağıtım | **DIŞ BAĞIMLILIK** | Kurulabilir ve doğrulanabilir artifact |
| 7 | PRD-7 — Performans/footprint | **DIŞ BAĞIMLILIK** | Hosted örnekler sonrası sürüm bütçeleri |
| 8 | PRD-8 — Gerçek kütüphane pilotları | **AKTİF** | GitHub beklerken ilerleyen yerel çalışma kanıtı |
| 9 | PRD-9 — Upstream/güvenlik/bakım | **BEKLİYOR** | Sürdürülebilir production işletimi |
| 10 | PRD-10 — RC/stable yayın | **BEKLİYOR** | İmzalı ve kanıtlı production release |

### Şu anki kritik yol

1. Final kanıt commit'inin required context'lerini yeniden yeşil doğrula ve
   final run/job bağlantılarını commit döngüsü yaratmadan PR açıklamasında tut.
2. Hazır Python 3.14 + HPy-development `SIGSEGV` raporunu proje sahibi açıkça
   onayladığında HPy upstream'e yayımla ve sonucu PRD-5 audit'ine bağla.
3. `aHPy-compiler` ad ayırma, gerçek TestPyPI upload'u ve ilk imzalı tag gibi
   owner-onaylı dış PRD-6 eylemlerini yayın yetkisi verilmeden uygulama.
4. Aynı release-candidate commit'inde en az beş benzersiz hosted performans
   raporu topla, fail-closed kalibrasyon önerisini incele ve eşikleri yeniden
   same-HEAD doğrula.
5. Hosted release bütçeleri kilitlenmeyi beklerken dört gerçek kütüphane
   pilotunun bağımsız yerel build/test/diagnostic işlerini ilerlet; yalnız
   hosted kanıt isteyen çıkış kapılarını açık bırak.

## Başlangıç durumu

- Başlangıç tarihi: 2026-07-28.
- Başlangıç commit'i: `0924dc88049a514382b2befaae7b70074645f25b`.
- PRD-0 CI uygulama commit'i: `e791c8983bcb1a3c38aa932617a91ea976cb5c55`.
- Çalışma dalı: `codex/ahpy-bootstrap`.
- Release dalı değildir; release politikası gereği production hattı daha sonra
  `ahpy/<cython-major>.<cython-minor>` biçiminde açılacaktır.
- Stabil yerel ortam: CPython 3.11.15 + HPy 0.9.0.
- Mevcut odaklı doğrulama: 440 compiler/seam testi, 530 quality-tool testi ve
  iki yorumlayıcıda 970 coverage testi.
- Universal backend Python modülleri için ölçülen satır kapsamı: %100.
- Quality-tool Python satır kapsamı CPython 3.11 ve 3.14'te %100; ayrı native,
  subprocess, portability ve hosted kapıları bu orana dahil edilmez.
- Bu oran generated C, native runtime, binary portability veya bütün Cython
  özelliklerinin %100 desteklendiği anlamına gelmez.
- Mevcut uygun sınıflandırma: unpublished preview.

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

- [x] İlk sürümün ürün seviyesini seç: `preview`, `beta`, `release candidate`
      veya `stable`.
- [x] İlk sürümün exact Cython base commit ve sürümünü belirle.
- [x] Desteklenen HPy sürümlerini tam commit/sürüm olarak belirle.
- [x] Desteklenen Python yorumlayıcı ve sürümlerini belirle.
- [x] Desteklenen OS/compiler matrisini belirle.
- [x] Desteklenen build frontendlerini belirle:
  - [x] Doğrudan build.
  - [x] setuptools/cythonize.
  - [x] PEP 517.
  - [x] CMake.
  - [x] Meson.
  - [x] scikit-build-core.
- [x] “Supported”, “partial”, “blocked” ve “rejected” terimlerini release
      notlarında kullanıcı açısından tanımla.
- [x] General Cython compatibility iddiası yapılmayacağını açıkça yaz.
- [x] PyPy/GraalPy aynı-binary desteği sağlanamazsa ilk sürümün Universal
      iddiasını daralt veya stable etiketi kullanma.
- [x] HPy 0.9 dış API engellerini ayrı bir known-limitations belgesinde kilitle.
- [x] Destek sözleşmesini `support-matrix.md`, `validation-matrix.md`, README,
      onboarding ve release policy ile eşitle.

### PRD-1 çıkış kapısı

- [x] Her kullanıcı özelliği tek bir support status'a sahip.
- [x] Her support status'ın testi, diagnostic'i veya dış engel kanıtı bağlı.
- [x] Release kapsamının dışında kalan hiçbir özellik dolaylı biçimde
      production iddiasına dahil edilmiyor.

## PRD-2 — Core compiler, ownership ve module-state kapılarını kapat

- [x] M2'de kalan her `return`, `break`, `continue`, `goto` ve exception
      çıkışında ownership/cleanup propagation'ı tamamla.
- [x] Python ile etkileşen kalan utility yollarına context propagation ekle;
      kanıtlanmış pure-C helper'ları context-free tut.
- [x] Her kalan ara HPy allocation/API çağrısından sonra kontrollü hata
      enjeksiyonu ekle.
- [x] Borrowed, owned, moved, closed, field, global ve context-constant
      handle durumlarının tamamını model/test et.
- [x] M3'te release kapsamına alınan module-function imzaları, container/call,
      control-flow, import/global/default ve exception ailelerinin parent
      maddelerini kapat.
- [x] M4'te release kapsamındaki bütün güvenli cache'leri interpreter-owned
      storage'a taşı.
- [x] Mutable Python state'in kayıt dışı C globalinde tutulmadığını kaynak ve
      davranış testleriyle doğrula.
- [x] Failed import, reload, teardown, concurrent import ve subinterpreter
      yollarını release kapsamı için tekrar çalıştır.
- [x] Generated source ve binary forbidden-symbol audit'lerini bütün maintained
      corpus üzerinde çalıştır.
- [x] Tam CPython C/C++ regression matrisini current release base üzerinde
      çalıştır ve farkları incele.

### PRD-2 çıkış kapısı

- [x] Release kapsamındaki core compiler özellikleri için açık ownership veya
      cleanup TODO'su kalmadı.
- [x] Normal/Trace/Debug, fault injection ve CPython regresyonları yeşil.
- [x] Bilinen leak, invalid handle, double-close veya borrowed-handle close
      hatası sıfır.

## PRD-3 — Pure HPy extension type kapısını kapat

- [x] M5 method/member/getset/slot parent maddesini release kapsamı için kapat.
- [x] Native member storage ve direct method access matrisindeki kalan türleri
      tamamla veya exact diagnostic ile sınır dışına al.
- [x] Constructor, `__cinit__`, `__init__`, allocation ve partial-object
      cleanup matrisini tamamla.
- [x] GC traversal, clear, finalization ve resurrection stresini bütün
      desteklenen yorumlayıcı şeritlerinde çalıştır.
- [x] Weakref, portable instance `__dict__`, context-bearing `__dealloc__` ve
      freelist politikasını HPy sürümüne göre kesin olarak destekle, engelle
      veya reddet.
- [x] Fused extension type politikasını ayrı olarak belirle.
- [x] Multiple inheritance için implement/reject kararını exact diagnostic ile
      kapat.
- [x] Forward-declared, cross-module generated, builtin base ve metaclass
      senaryolarını ayrı ayrı implement/reject et.
- [x] Variable-size layout'ların fail-closed kaldığını doğrula.
- [x] Release kapsamındaki bütün special method ve numeric/sequence/mapping
      slotlarını semantic, inheritance ve failure-path testleriyle kapat.
- [x] Type, field, descriptor ve finalizer durumunu en az üç subinterpreter
      altında doğrula.

### PRD-3 çıkış kapısı

- [x] Extension-type suite bütün desteklenen yorumlayıcı/platformlarda yeşil.
- [x] Traverse/clear/finalize/cyclic-GC Debug testleri temiz.
- [x] Kapsam dışındaki her type özelliği source-located diagnostic üretiyor.

## PRD-4 — Advanced Cython ailelerini tek tek sonuçlandır

Her aile için yalnızca iki kabul edilebilir sonuç vardır:

1. Ownership/context tasarımı, implementation, normal/Trace/Debug testleri ve
   destek kanıtıyla enabled.
2. Sürüm belirtilen diagnostic, test ve migration guidance ile
   blocked/rejected.

- [x] Generic iterator protokolü ve pure-type `__iter__`/`__next__`.
- [x] Generator, `yield`, `yield from`, `send`, `throw` ve `close`.
- [x] Native coroutine, `async`/`await` ve async generator.
- [x] Buffer producer acquisition/release ownership modeli.
- [x] Buffer consumer ve typed memoryview.
- [x] Fused types ve specialization dispatcher.
- [x] Genel `nogil`, execution re-entry ve exception reacquisition.
- [x] `prange`, OpenMP, synchronization ve free-threading.
- [x] Python state taşıyan C callback'leri.
- [x] Capsules ve cross-module public/C API.
- [x] C++ compilation, exception translation, STL ve RAII cleanup.
- [x] Profiling, tracing, coverage, monitoring ve traceback üretimi.
- [x] Pickling, signatures, annotations, code object ve introspection.
- [x] Embedding ve birden fazla embedded HPy module.
- [x] NumPy ve diğer CPython-only third-party C API politikası.
- [x] Set construction/mutation HPy public API eksikliği.
- [x] Genel exception state: `except as`, bare reraise, traceback, cause,
      chaining, `else`, `finally` ve nested handlers.
- [x] HPy method function-object/`__defaults__`/code-object introspection
      eksikleri.

### PRD-4 çıkış kapısı

- [x] Hiçbir advanced aile belirsiz veya yarım enabled durumda değil.
- [x] Release kapsamındaki aileler tam testli; diğerleri deterministik ve
      belgelenmiş şekilde fail-closed.

## PRD-5 — Universal portability ve native-memory kanıtını tamamla

- [x] Aynı hash'e sahip `.hpy0` binary'yi desteklenen bütün yorumlayıcılarda
      çalıştır.
- [x] PyPy HPy bridge/import problemini upstream durumuyla birlikte çöz veya
      destek kapsamından çıkar.
- [x] GraalPy HPy bridge/native `.hpy0` import-hook problemini çöz veya destek
      kapsamından çıkar.
- [x] Aynı binary için normal, Trace ve Debug semantiğini karşılaştır.
- [x] Stable HPy 0.9 şeridini bütün desteklenen platformlarda tekrar doğrula.
- [x] Pinned HPy development şeridini Python 3.11 üzerinde doğrula.
- [ ] Python 3.14 + HPy development `SIGSEGV` durumunu minimal reproducer ile
      sınıflandır; dış sorun ise upstream'e bildir ve allowed-failure tut.
- [x] CPython prerelease + HPy stable nightly sonucunu izlemeye devam et;
      nightly sonucu stable destek iddiasına dönüştürme.
- [x] Linux Valgrind/LSan positive control ve gerçek corpus kapısını release
      run'ında çalıştır.
- [x] Windows AppVerifier/full-page-heap artifact'ını incele, injection ve
      positive-control kanıtından sonra kapıyı promote et.
- [x] ASan ve UBSan'ı bütün uygulanabilir native derleyici ailelerinde çalıştır.
- [x] Uygulanabilen platformlarda TSan/free-threading politikasını belirle.
- [x] Portability artifact hash, binary imports ve source boundary raporlarını
      release provenance'a ekle.

### PRD-5 çıkış kapısı

- [x] İlan edilen cross-interpreter matrisinde aynı binary yeşil.
- [x] Bütün zorunlu platform/compiler/sanitizer işleri clean build'den yeşil.
- [x] Native-memory positive control'leri gerçek kapıların çalıştığını
      kanıtlıyor.

## PRD-6 — Paketleme ve dağıtım hattını production seviyesine getir

- [ ] `aHPy-compiler` dağıtım adını proje sahibi hesabında ayır.
- [x] Version metadata'ya exact Cython base, aHPy commit ve HPy compatibility
      bilgisini ekle/doğrula; sdist ve wheel Core Metadata'sı üç exact
      provenance URL'si taşır, arşiv `.gitrev` kaydı fail-closed doğrulanır.
- [x] Clean source tree'den sdist ve frontend wheel üret.
- [x] Sdist/wheel member safety, completeness ve license/provenance audit'ini
      çalıştır.
- [x] İki bağımsız clean root'ta byte-reproducible frontend artifact üret.
- [x] Fresh venv içinde no-index install/uninstall/reinstall testi çalıştır.
- [x] PEP 517'in yanlışlıkla upstream Cython veya başka `ahpy` paketini
      çözümlemediğini doğrula.
- [x] Direct build, setuptools, CMake, Meson ve scikit-build-core
      dokümantasyonlarını temiz ortamda yeniden çalıştır; macOS ARM64/CPython
      3.11/HPy 0.9 kapılarının tamamı 2026-07-29'da tekrar yeşil.
- [x] CMake/Meson/scikit-build Windows ve cross-build kapsamını tamamla veya
      açıkça sınırla; preview sözleşmesi bu yolları Linux x86-64 hosted ve
      macOS ARM64 local kanıtla sınırlar, Windows/cross-build'i support
      kapsamına almaz.
- [x] HPy/PyPA standart Universal wheel/tag sözleşmesini seçmeden özel tag
      üretme veya CPython-tagged wheel'i Universal olarak adlandırma; preview
      sözleşmesi mevcut host-tagged example wheel'i yalnız packaging smoke
      testi olarak sınırlar.
- [x] Universal wheel standardı hazır değilse `.hpy0` portability artifact
      dağıtım yolunu açıkça tanımla ve stable release kapsamını buna göre
      sınırla; aynı `.hpy0` dosyası release-evidence artifact'ıdır, yayımlanmış
      installable Universal wheel iddiası değildir.
- [ ] Standardize Universal wheel mevcut olduğunda onun reproducibility,
      install ve cross-interpreter testlerini ekle.
- [x] Artifact checksum, SBOM, license listesi ve build provenance üret;
      release gate sdist, frontend/example wheel ve exact HPy/setuptools
      wheel'leri için doğrulanmış `SHA256SUMS`, SPDX 2.3 JSON,
      machine-readable lisans envanteri ve exact source/build
      `provenance.json` içeren fail-closed bundle üretir.
- [ ] Release artifact'lerini imzala ve doğrulama talimatını yayımla;
      tag-only keyless Sigstore/GitHub OIDC workflow'u, SLSA + SPDX
      attestation'ları ve online/offline doğrulama politikası hazırdır, kapı
      ilk onaylı `ahpy-v<version>` tag'i gerçekten imzalanıp doğrulanana kadar
      açık kalır.
- [x] PyPI/TestPyPI yayınlama ve geri çekme/yeniden yayınlamama politikasını
      belgeleyip dry-run yap; fail-closed seçici yalnız frontend sdist/pure
      wheel'i hazırladı, hash'ler eşleşti ve pinned Twine 6.2.0 strict
      metadata kontrolü geçti; gerçek TestPyPI/PyPI upload'u açıkça dış,
      owner-onaylı bir release eylemidir.

### PRD-6 çıkış kapısı

- [ ] Yeni kullanıcı checkout bağımlılığı olmadan ilan edilen yolu kurup
      örneği build/import edebiliyor.
- [ ] Artifact kimliği, kaynağı, hash'i ve destek kapsamı doğrulanabiliyor.
- [ ] Dağıtım metadata'sı Universal destek konusunda yanıltıcı değil.

## PRD-7 — Release performans ve footprint bütçelerini sabitle

- [x] Benchmark workflow artifact/summary hatasını PRD-0 kapsamında kapat.
- [x] Generated Universal ve eşdeğer handwritten HPy implementasyonlarını bütün
      release benchmark ailelerinde tut; desteklenen sequence-index iteration
      ailesi de iki tarafta aynı semantic oracle ile ölçülür.
- [x] Classic Cython, HPy CPython ABI ve HPy Universal ABI sonuçlarını ayrı
      raporla; cross-ABI aggregate oran yayımlama.
- [ ] Calls, arithmetic, containers, attributes, exceptions, types ve
      external-C için hosted history biriktir.
- [x] Release kapsamında desteklenen sequence-index iteration benchmark'ını
      ekle; HPy 0.9 public buffer consumer API sunmadığı için memoryview'i
      “blocked/non-comparable” ve performans sayısı olmadan bırak.
- [x] Compile time, C compiler time, generated C boyutu, binary boyutu ve peak
      memory ölç.
- [ ] Gürültü analiziyle mutlak/nispi release eşiklerini versiyonla.
  - [x] Her yeni rapora exact kaynak/GitHub run provenance ekle; en az beş
        benzersiz, başarılı, aynı-commit ve aynı-kohort hosted rapor olmadan
        bütçe önerisi üretmeyen fail-closed kalibratörü ekle.
  - [x] Tek seçilmiş commit için beş izole hosted sample çalıştıran, yalnız
        read-only izinli ve bütün sample'lar geçmeden proposal üretmeyen manual
        kalibrasyon workflow'unu ekle.
  - [x] Frontend/native build süresi, generated/reference peak RSS oranı ve
        large-type frontend/O0 ölçümlerini aynı hosted kohort içinde
        fail-closed doğrula ve proposal-only tavanlar üret.
  - [x] Geçici tavanları machine-readable `regression`/non-release policy olarak
        sınıflandır; schema-v3 benchmark/proposal kanıtında policy'yi taşı ve
        hosted minimumunu CLI ile zayıflatmayı reddet.
  - [x] Gelecekteki approved release policy'sini `hosted-checkout` modeline
        bağla; calibration-source commit'ini policy'de, exact current candidate
        commit'ini immutable raporda tut ve source commit / GitHub SHA
        uyuşmazlığını oranlara bakmadan reddet.
  - [x] Her schema-v3 rapora yalnız budget path/policy değil exact validated
        runtime, footprint, environment, measurement ve native compile
        contract'ını göm; cohort contract drift'ini reddet ve proposal'a taşı.
  - [x] Regression policy'de uncalibrated absolute limitleri yasakla; approved
        release policy için frontend/native build time, generated peak RSS ve
        oranı, large-type frontend/O0 sürelerinden oluşan exact altı positive
        finite ceiling'i zorunlu ve fail-closed uygula.
  - [x] Schema-v3 proposal'daki on runtime, üç footprint ve altı absolute
        tavanı release TOML ile birebir karşılaştıran; input contract,
        calibration-source, environment/measurement/native policy veya sample
        floor drift'ini reddeden read-only promotion validator ekle.
  - [ ] Aynı release-candidate HEAD'i için hosted geçmişi topla, headroom
        önerisini incele ve release eşiklerini ayrı bir same-HEAD koşuyla
        doğrula.
- [x] Eşik aşımında fail-closed CI ve anlamlı rapor üret.
- [x] HPy runtime/interpreter maliyetini aHPy overhead'inden ayrı göster.
- [x] Ownership kanıtı olmadan Dup/Close optimizasyonu yapma; call-frame
      lifetime kanıtı yalnız incoming sequence argümanını borrow eder, rebind
      edilebilir owned local kaynakları materialize etmeye devam eder.

Mevcut `performance-budgets.toml` artık açıkça yalnız regresyon korumasıdır:
`release_enforced = false`, calibration hosted geçmişi bekliyor,
`candidate_binding = "unbound"` ve calibration source boştur. Loader bu
alanların çelişkili
kombinasyonunu; kalibratör ise farklı policy'leri veya beşten düşük bir CLI
minimumunu reddeder. Bu hazırlık release eşiği uydurmaz; gerçek hosted history,
maintainer incelemesi ve same-HEAD doğrulaması açık kalır.
Approved duruma geçirilecek gelecekteki policy de tek başına yeterli değildir:
policy reviewed calibration-source commit'ini kaydeder; mevcut candidate hash'i
öz-referanslı biçimde policy'ye yazmak yerine immutable benchmark raporu taşır.
Gate hosted execution ile source commit / `GITHUB_SHA` eşitliğini zorunlu tutar;
local veya stale-checkout kanıtı release sonucu olamaz.
Artifact ayrıca uygulanan tavanların tamamını içerir; repository dosyası daha
sonra değişse bile hangi contract'ın geçtiği doğrulanabilir. Kalibratör compact
policy ile embedded contract, runtime ortamı/measurement/enforcement ve beş
sample arasındaki exact contract eşitliğini fail-closed denetler.
Mevcut regression contract'ı kasıtlı olarak `release_absolute` içermez. Bu
tablo yalnız hosted proposal incelenip policy release'e geçirildiğinde altı
zorunlu ölçümle eklenebilir; eksik, non-finite veya aşılmış evidence release
gate'ini kapatır.
Promotion validator bu altı alanla birlikte on runtime ve üç footprint
tavanının proposal'dan aynen geldiğini ispatlar; budget dosyasını değiştirmez,
maintainer onayı veya current-candidate same-HEAD hosted kanıtı yerine geçmez.

### PRD-7 çıkış kapısı

- [ ] Bütün yayımlanan bütçeler aynı release candidate üzerinde yeşil.
- [ ] Sonuçlar timestamped, immutable CI artifact olarak saklanıyor.
- [x] Desteklenmeyen aileler için uydurma performans sayısı yayımlanmıyor.

## PRD-8 — Gerçek kütüphane pilotlarını tamamla

- [x] Doğrudan Python C API kullanmayan saf Cython pilotunu seç.
- [x] Python-independent C kütüphanesini saran pilotu seç.
- [x] Extension type, GC ve inheritance kullanan pilotu seç.
- [x] CPython/NumPy C API nedeniyle bilerek blocked olacak pilotu seç.
- [x] Her pilot için upstream sürüm/commit ve lisans kaydı tut.
- [x] Her pilot için gereken kaynak değişikliklerini kaydet.
- [ ] Her pilotun build, test, normal/Trace/Debug ve performance sonuçlarını
      kaydet.
- [x] Ortak portlama değişikliklerini backend desteğine veya migration
      kuralına dönüştür.
- [x] Blocked pilotun source-located diagnostics kalitesini doğrula.
- [ ] CI artifact'lerinden compatibility dashboard üret.
- [x] Library-author porting guide yayımla.
- [x] Bug/compatibility issue template ekle.
- [x] HPy conformance corpus'unu kullanıcının programlama diliyle paylaşırken
      Cython frontend internallerine bağımlılık oluşturma.

Yerel ara kanıt: pinned `cython-package-example` 0.1.7 port fixture'ının üç
modülü ilan edilen setuptools Universal yolunda generate/native-build,
source/binary audit, seçili upstream semantiği ve normal/Trace/Debug
`LeakDetector` kapılarını geçiyor. Host-tagged wheel içerik audit'i, dependency
olmadan isolated target kurulumu, kurulu normal/Trace/Debug çalıştırmaları ve
aynı süreçteki eşdeğer Python fonksiyonlarına karşı provenance-bound yedi
tekrarlı `axpy`/Fibonacci ölçümü de yerelde geçiyor; hosted artifact gelmeden
PRD-8 çıkış kapısı işaretlenmeyecek ve yerel ölçüm release bütçesi sayılmayacak.
Pinned bezier `_speedup.pyx` kaynağının SHA-256 değeri
`f99e5053f1c942bbc443fa3399c1c67243c46cf078c664a00cc9433ae2993a05` olarak
doğrulandı; NumPy C-API kuralı exact upstream satırlarında `37:1` ve `38:1`
konumlarını üretir ve runner bu iki konumdan biri kayarsa expectation'ı
fail-closed kapatır.
Pinned murmurhash commit'inin fiziksel header yolları
`murmurhash/include/murmurhash/` olarak düzeltildi ve pristine checkout ile
doğrulandı. Exact upstream `MurmurHash3.cpp`/header kullanan fixed-width scalar
adapter generate/native-build, source/binary audit, normal/Trace/Debug ve
conversion-failure kapılarını yerelde geçiyor; pointer yalnız C++ shim içinde
kalır ve upstream `hash(str | bytes)` API'si destekleniyor diye işaretlenmez.
Desteklenen `hash_u64` scalar yüzeyi aynı süreçteki bağımsız Python oracle'ına
karşı yedi medyan örnekle ölçülür; ortam provenance'ı zorunludur ve sonuç
release bütçesi değildir.
Pinned frozenlist kaynağından türetilen supported-subset port; object-valued
HPy field GC döngüsü, same-module inheritance, mutation/freeze/hash semantiği
ve constructor failure cleanup kapılarını normal/Trace/Debug altında geçiyor.
C++ atomic/free-threading, iterator, rich-compare, copy/deepcopy ve
MutableSequence registration kapsam dışı olarak raporlanıyor. Pilot ayrıca
Universal `__hash__` slotunda fitting büyük tamsayıların ikinci kez hash'lendiği
gerçek emitter hatasını ortaya çıkardı; direct `HPy_hash_t` conversion,
overflow fallback ve `-1`→`-2` davranışı düzeltilip regresyonlandı.
Desteklenen construct/mutate/freeze/hash altkümesi eşdeğer Python list/tuple
workload'una karşı aynı fail-closed performans şemasıyla ölçülür; kapsam dışı
yüzeylere oran veya performans iddiası taşınmaz.
Tam dört-pilot pristine checkout/scan matrisi ile üç port integration raporu
yerelde tek dashboard'a kapı bazında birleştirildi: cypack `pass`, murmurhash
`partial-scalar-adapter`, frozenlist `supported-subset`, bezier ise beklenen
`blocked` sonucunu veriyor. Workflow aynı dört JSON girdisini ve üretilen
Markdown dashboard'u immutable artifact grubuna ekliyor; GitHub yazma limiti
nedeniyle hosted artifact kanıtı ve ilgili checkbox açık kalıyor.
Dashboard başarılı performans kapısı için eksiksiz sonlu örneklem, karşılaştırma
kimliği, ortam provenance'ı ve `budget_enforced = false` ister; bezier matrisi
ise NumPy C-API sınırı nedeniyle gerekçeli `blocked` kaydı üretir ve sayı üretmez.
Frontend-independent `ahpy-universal-conformance-v1` sözleşmesi 21 semantik
vakayı checksummed JSON'a ayırıyor; standart-kütüphane runner'ı yalnız açık
surface→module eşlemesi kullanıyor ve hiçbir Cython import'u, `.pyx` yolu veya
frontend node'u gerektirmiyor. Aynı modül(ler) normal/Trace/Debug raporlarına
bağlanabilir; ABI audit, cross-interpreter ve fault-injection kapıları ayrıca
zorunlu kalıyor.
Pilotlarda tekrar eden port adımları artık genel migration sözleşmesidir:
module-level `cdef`/`cpdef` için `compiled-entry-point`, relative Cython C-API
importları için `cython-module-cimport`, `libcpp` state için
`cpp-runtime-boundary`; mevcut `native-pointer-boundary`,
`direct-cpython-cimport` ve `numpy-c-api` kuralları diğer üç pilotu kapsar.
Cypack ve frozenlist pinned initial-scan beklentileri bu kesin action ID'lerini
zorunlu tutar; generic `unsupported-source-node` sonucu artık bu geçişleri
gizleyemez.

### PRD-8 çıkış kapısı

- [ ] Dört pilotun raporu ve yeniden çalıştırılabilir CI kanıtı yayımlandı.
- [x] En az bir gerçek üçüncü taraf proje ilan edilen production yolunda
      source/binary/Debug kapılarını geçiyor.

## PRD-9 — Upstream, güvenlik ve sürdürülebilir bakım

- [ ] Cython maintainer'larıyla backend-neutral seam tasarımını görüş.
- [ ] Backend-neutral refactor'ları küçük bağımsız upstream PR'larına ayır.
- [ ] HPy API eksiklerini minimal reproducer ile upstream issue/PR olarak aç.
- [ ] PyPy/GraalPy bridge sorunlarını ilgili upstream projelere taşı.
- [ ] Cython upstream rebase log'unu ve conflict kararlarını güncel tut.
- [ ] Release branch/backport politikasını uygula.
- [ ] Security policy ve özel vulnerability reporting kanalını yayımla.
- [x] Desteklenen Cython, HPy, Python, OS ve compiler sürüm politikasını yayımla.
- [ ] Dependency update ve security scanning otomasyonunu ekle.
- [ ] Third-party license/provenance envanterini release artifact'e bağla.
- [x] User, contributor, architecture, debugging ve release belgelerini
      tamamla.
- [x] Deprecation, compatibility-break ve migration politikasını tanımla.
- [x] Periyodik Cython/HPy/interpreter/compiler/platform update cadence'i
      tanımla.
- [x] Maintainer ownership, issue triage ve release sorumlularını belirle.

Yerel PRD-9 hazırlığı: `maintenance-policy.toml` artık tek maintainer/bus-factor
riskini, preview destek/EOL sınırını, release/backport kurallarını, en az bir
stable release-cycle deprecation süresini ve aylık/çeyreklik update cadence'ini
machine-readable biçimde sabitliyor; `maintenance_policy.py` referans belgeleri
ve otomasyon dosyalarını fail-closed doğruluyor. `CODEOWNERS` mevcut project,
security ve release sahibini açıkça kaydediyor. Yeni `ahpy-security.yml`,
Dependency Review v5.0.0 ve CodeQL v4.36.0 `security-extended` Python/C++
taramalarını immutable SHA'larla PR/push/weekly kapılarına bağlıyor; Dependabot
Actions ile üç Python dependency kökünü aylık izliyor. Hosted ilk taramalar ve
security artifact kanıtı başarıyla tamamlanmadan ilgili publication/automation
checkbox'ları açık kalır.
Append-only `rebase-log.toml`, mevcut
`b99cb0e3b5425e11414cadd24168a6cc850e8000` baseline seçimini gerçek bir rebase
gibi göstermeden kaydediyor. `rebase_log.py` gelecekteki accepted geçişlerin
önceki commit'ten zincirlenmesini, conflict dosyası/sınıfı/kararını, kanıt
belgelerini ve final base'in package/release metadata'sıyla eşleşmesini zorunlu
tutuyor; henüz yeni upstream base kabul edilmediği için rebase checkbox'ı açık.
`debugging.md`, source diagnostic'ten generated C/native link/import/runtime ve
ownership sınırına kadar ilk bozulan aşamayı koruyan tek troubleshooting akışını
veriyor. `upstream-dependencies.md` ise HPy 3.14 handwritten reproducer'ı, HPy
#488 bağlantısını, PyPy/GraalPy bridge/loader ve diğer public-API boşluklarını
hosted kanıt / prepared report / filed issue ayrımıyla merkezileştiriyor;
owner onayı olmadan hiçbir yeni upstream issue yayımlanmadı.
İlk backend-neutral dependency inversion da yerelde uygulanmıştır:
`Cython.Build` backend adıyla idempotent/fail-closed bir build hazırlık hook'u
kaydeder ve installed entry point'ten tek provider keşfeder; HPy 0.9 loader
uyumluluğunu `ahpy_hpy_compat` entegrasyon tarafından kaydeder ve Cython build
core artık hiçbir `ahpy_*` modülünü adlandırmaz veya import etmez.
Eşzamanlı başlatılan CPython ve Universal derlemeleri de context-local runtime
seçiminin generated output'a çapraz sızmadığını kanıtlar; coverage tracer worker
thread'lerini ölçer ve dış trace hook'larını geri yükler.
`ModuleNode` artık HPy writer'ı veya backend enum'unu seçmez; immutable runtime
servisinden doğrulanmış tam-module emitter sözleşmesini alır. CPython yolu
mevcut default writer/oracle olarak aynı kalırken Universal emitter kendi
validation, render ve output-file yaşam döngüsü sorumluluğunu taşır.
`docs/ahpy/upstream-seam-plan.md` bu değişikliği altı bağımsız upstream dilimine,
downstream-only politikalara, kanıt kapılarına ve maintainer sorularına ayırır;
görüşme veya açılmış upstream PR olmadığı için ilgili checkbox'lar açık kalır.
PyPy/GraalPy taslakları artık Cython frontend'inden bağımsız
`minimal_universal.c` oracle'sını artifact'in ilk iki izole aşamasında çalıştırır;
CPython 3.11/HPy 0.9 yerel semantik ve iki-clean-build reproducibility kanıtı
yeşildir. Smoke, hata halinde dahi doğrulanmış hash/provenance, sıralı stage
çıktıları ve exit/signal sınıfını JSON'a yazar; workflow bunu `if: always()` ile
saklar. İlk hosted minimal sonuç ve exact hata sınıfı gelmeden bu raporlar
yayıma hazır veya upstream'e taşınmış sayılmaz.
`release_contract.py` machine-readable preview sözleşmesinin exact şemasını;
dağıtım/Cython/HPy/Python pinlerini; altı platform, yedi frontend ve hosted run
kimliklerini; workflow ile kullanıcı belgesindeki karşılıklarını fail-closed
doğruluyor. Universal CI bu CLI'yi doğrudan çalıştırır; böylece sözleşme drift'i
yalnız monolitik test assertion'larına veya tek kişinin bilgisine bağlı değildir.
`documentation-contract.toml` kullanıcı, contributor, architecture, debugging
ve release için 28 zorunlu belgeyi beş exact kategoriye ayırır; gerekli
operational heading'leri, ana doküman index erişimini ve 72 yerel Markdown
linkini fail-closed doğrular. Universal CI schema-versioned JSON'u packaging
artifact grubunda saklar; eksilen, index dışına düşen veya kırık link taşıyan
belge production kapısını kapatır.
`maintenance-policy.toml` ve `maintenance.md` artık source, runtime semantics,
generated source, artifact, CLI/configuration ve diagnostic uyumluluk
yüzeylerinin tamamını sınıflandırır. Preview ve stable notice/removal sınırları,
changelog/migration/release-note/support-matrix kanalları, stable action ID,
old/new test ve replacement-or-rationale kanıtları ile yalnız
correctness/security için owner-onaylı acil istisna fail-closed doğrulanır.
Exact sürüm/OS/compiler desteği release/support contract'ında, aylık/çeyreklik
update cadence'i ve project/security/release sahipliği aynı bakım sözleşmesinde
tek kaynak olarak yayımlanır.

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
- [x] Geri çekme, security fix ve backport prosedürünü dry-run et.
- [ ] Stable sürümü yalnızca bütün aşağıdaki definition-of-done maddeleri
      tamamlandığında tag'le.

Yerel no-publication recovery drill; izole bir Git deposunda `ahpy/3.2`
release-line fixture'ı, kaynak correctness commit'i ve ayrı backport topic
branch'ı oluşturup `cherry-pick -x` provenance'ını, orijinal regresyon testini,
değişmeyen support tier'ı ve mandatory-matrix zorunluluğunu doğruladı.
Machine-readable politika normal defect için gerekçeli yank + yeni immutable
version, delete için yalnız credential disclosure/malware/legal demand ve
security fix için disclosure'a kadar private koordinasyon zorunluluğunu
fail-closed uygular. Bu dry-run gerçek branch, tag, yank veya upload yapmaz;
Universal CI JSON kaydını packaging artifact grubunda saklayacaktır.

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

Bir sonraki aktif yerel hedef PRD-7 release performans/footprint bütçeleridir;
PRD-5 upstream raporu ile PRD-6 name/sign/upload adımları açık owner yetkisi
gerektiren dış eylemler olarak bekler.
