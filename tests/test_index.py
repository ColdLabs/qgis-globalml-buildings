import pytest

from globalml_buildings_downloader import index

HEADER = 'Location,QuadKey,Url,Size,UploadDate\n'


def test_sizes_are_binary_units():
    assert index.parse_size('512B') == 512
    assert index.parse_size('8.2KB') == round(8.2 * 1024)
    assert index.parse_size('27.8MB') == round(27.8 * 1024**2)
    assert index.parse_size('1.2GB') == round(1.2 * 1024**3)
    assert index.parse_size('300MB') == 300 * 1024**2


def test_size_matches_a_measured_download():
    # The Portugal tile of 031332213 is listed as 979.4KB and is 1,002,933 bytes.
    assert abs(index.parse_size('979.4KB') - 1002933) < 0.05 * 1024


@pytest.mark.parametrize('text', ['', 'KB', '12', '1.2TB', '1,2MB', '-3KB'])
def test_unreadable_sizes_are_rejected(text):
    with pytest.raises(index.BadIndex):
        index.parse_size(text)


def test_border_quadkey_keeps_every_region():
    text = HEADER + (
        'Europe,031332213,https://h/e.csv.gz,22.4KB,2026-08-13\n'
        'Portugal,031332213,https://h/p.csv.gz,979.4KB,2026-08-13\n'
        'Spain,031332213,https://h/s.csv.gz,27.8MB,2026-08-13\n'
        'Spain,031332212,https://h/s2.csv.gz,1.0MB,2026-08-13\n'
    )
    tiles = index.parse(text)
    assert sorted(tiles) == ['031332212', '031332213']
    border = tiles['031332213']
    assert [t.region for t in border] == ['Europe', 'Portugal', 'Spain']
    assert [t.url for t in border] == [
        'https://h/e.csv.gz',
        'https://h/p.csv.gz',
        'https://h/s.csv.gz',
    ]
    assert border[2].size_bytes == round(27.8 * 1024**2)
    assert tiles['031332212'] == [
        index.Tile('Spain', '031332212', 'https://h/s2.csv.gz', 1024**2)
    ]


def test_hyphenated_regions_are_accepted():
    tiles = index.parse(HEADER + 'Guinea-Bissau,033,https://h/g,1KB,x\n')
    assert tiles['033'][0].region == 'Guinea-Bissau'


@pytest.mark.parametrize('region', ['..', '../etc', 'a/b', ''])
def test_region_that_is_not_a_folder_name_is_rejected(region):
    with pytest.raises(index.BadIndex):
        index.parse(HEADER + '%s,033,https://h/x,1KB,x\n' % region)


def test_quadkey_with_other_digits_is_rejected():
    with pytest.raises(index.BadIndex):
        index.parse(HEADER + 'Spain,0314,https://h/x,1KB,x\n')


def test_missing_column_is_rejected():
    with pytest.raises(index.BadIndex, match='Size'):
        index.parse('Location,QuadKey,Url\nSpain,033,https://h/x\n')


def test_release_comes_from_the_url_folder():
    assert index.release(index.INDEX_URL) == '2026-08-13'
    assert index.release('https://h/a/2027-01-02/dataset-links.csv') == (
        '2027-01-02'
    )
    with pytest.raises(index.BadIndex):
        index.release('https://h/../dataset-links.csv')
    with pytest.raises(index.BadIndex):
        index.release('https://h/dataset-links.csv')


def test_parses_the_real_index():
    import os

    path = os.environ.get('GLOBALML_INDEX')
    if not path:
        pytest.skip('set GLOBALML_INDEX to a downloaded dataset-links.csv')
    with open(path, encoding='utf-8') as f:
        tiles = index.parse(f.read())
    assert sum(len(v) for v in tiles.values()) == 30340
    assert [t.region for t in tiles['031332213']] == [
        'Europe', 'Portugal', 'Spain'
    ]
