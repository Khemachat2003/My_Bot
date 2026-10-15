import re, sys

css = open(sys.argv[1], encoding='utf-8').read()

# หา media headers ทั้งหมด (รองรับ syntax เก่า/แบบ range) แล้วบอกว่า key อยู่ใน block ไหน
medias = [(m.start(), m.group(0)) for m in re.finditer(r'@media[^{]*\{', css)]
print('media count:', len(medias))
for i, (pos, head) in enumerate(medias):
    end = medias[i + 1][0] if i + 1 < len(medias) else len(css)
    seg = css[pos:end]
    for key in ['tbl-cards', 'nav-toggle', 'drawerScrim', 'j-hero', 'sidebar', '769']:
        if key in seg and key in head or (key in seg and key != '769'):
            print(f'  [{i}] {head.strip()[:40]} -> has {key}: {seg.count(key)}x')

