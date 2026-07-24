"""洗版百分制质量评分测试。"""
from onefive.services.quality_score import (
    aggregate_quality_scores,
    calculate_quality_score,
    generate_video_tags,
    get_quality_level,
    score_quality_breakdown,
)


class TestQualityScore100:
    def test_remux_beats_web_same_4k(self):
        remux = "Movie.2020.2160p.UHD BluRay REMUX DV HDR.H265.TrueHD.Atmos.7.1-Group.mkv"
        web = "Movie.2020.2160p.WEB-DL DV.H265.DDP.Atmos.5.1.Netflix-HiveWeb.mkv"
        rs = calculate_quality_score(remux)
        ws = calculate_quality_score(web)
        assert 0 <= rs <= 100 and 0 <= ws <= 100
        assert rs > ws, f"remux={rs} web={ws}"

    def test_bare_remux_beats_full_web(self):
        remux = "Show.S01E01.2160p.UHD BluRay REMUX.mkv"
        web = "Show.S01E01.2160p.WEB-DL DV.H265.DDP.Atmos.5.1-Group.mkv"
        rs = calculate_quality_score(remux)
        ws = calculate_quality_score(web)
        assert rs > ws, f"bare remux={rs} full web={ws}"

    def test_score_cap_100(self):
        name = "A.2020.4320p.UHD BluRay REMUX DV HDR10+.H265.TrueHD.Atmos.7.1-IMAX.mkv"
        assert calculate_quality_score(name) <= 100

    def test_size_ignored(self):
        name = "A.2020.2160p.WEB-DL.H265.DDP.5.1.mkv"
        assert calculate_quality_score(name, size=0) == calculate_quality_score(name, size=90 * 1024**3)

    def test_tags_use_rename_vocab(self):
        name = "A.2020.2160p.UHD BluRay REMUX DV.H265.TrueHD.Atmos.7.1-Group.mkv"
        tags = generate_video_tags(name)
        assert "2160p" in tags
        assert any("REMUX" in t for t in tags)
        assert any("DV" in t for t in tags)
        assert "H265" in tags

    def test_levels(self):
        assert get_quality_level(95) == "优秀"
        assert get_quality_level(80) == "良好"
        assert get_quality_level(65) == "一般"
        assert get_quality_level(40) == "较差"

    def test_aggregate_p75(self):
        assert aggregate_quality_scores([10]) == 10
        assert aggregate_quality_scores([10, 90]) == 90
        # 4 samples p75
        assert aggregate_quality_scores([10, 20, 30, 100]) >= 30

    def test_breakdown_sums(self):
        name = "A.2020.1080p.BluRay.H264.AAC.mkv"
        b = score_quality_breakdown(name)
        assert b.total == b.resolution + b.source + b.hdr + b.audio + b.codec_extra
        assert b.total == calculate_quality_score(name)
