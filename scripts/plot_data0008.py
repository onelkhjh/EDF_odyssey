"""Create time-series SVGs from validated DATA0008 SD records."""
from pathlib import Path
import sys
import math
import statistics
import html
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from tms_pc.communication.firmware_log import iter_records

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'recordings/20261027_221125_893648_hardware'
records = list(iter_records(r'D:\DATA0008.BIN'))
reports = [r for _, _, _, r in records]
times = [r.telemetry.runtime - reports[0].telemetry.runtime for r in reports]
channels = [
    ('rpm', 'RPM (rpm)', [r.rpm for r in reports], '#7c3aed'),
    ('voltage', 'EDF voltage (V)', [r.thruster.voltage_edf for r in reports], '#2563eb'),
    ('current', 'EDF current (A)', [r.thruster.current_edf for r in reports], '#059669'),
]
command = ('command', 'Throttle command (%)', [r.status.thrust_command for r in reports], '#2563eb')


def svg(name, panels):
    height = 90 + 290 * len(panels)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="{height}" viewBox="0 0 1100 {height}">',
             f'<rect width="1100" height="{height}" fill="white"/>',
             '<g font-family="sans-serif" font-size="16" fill="#111827">',
             '<text x="90" y="30">DATA0008.BIN - elapsed time since SD recording start</text>']
    for i, (key, label, values, color) in enumerate(panels):
        top = 80 + 290 * i
        good = [v for v in values if math.isfinite(v)]
        low, high = min(0, min(good)), max(good)
        high = 100 if key == 'command' else high + max((high-low)*.08, 0.01)
        low -= (high-low)*.03 if low < 0 else 0
        parts.append(f'<text x="90" y="{top-15}">{html.escape(label)}</text>')
        for k in range(6):
            y = top + 210 * k / 5
            value = high - (high-low)*k/5
            x = 90 + 935*k/5
            parts.extend([f'<path d="M90 {y:.2f} H1025" stroke="#e5e7eb"/>',
                          f'<text x="80" y="{y+5:.2f}" text-anchor="end">{value:.5g}</text>',
                          f'<text x="{x:.2f}" y="{top+235}" text-anchor="middle">{times[-1]*k/5:.2f}</text>'])
        points = ' '.join(f'{90+935*t/times[-1]:.2f},{top+210*(high-v)/(high-low):.2f}' for t,v in zip(times,values) if math.isfinite(v))
        parts.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="1.5"/>')
        parts.append(f'<text x="558" y="{top+262}" text-anchor="middle">Elapsed time (s)</text>')
    parts.append('</g></svg>')
    target = OUT / name
    target.write_text('\n'.join(parts), encoding='utf-8')
    ET.parse(target)
    print(target)


svg('DATA0008_rpm_voltage_current_time.svg', [command, *channels])
for channel in channels:
    svg(f'DATA0008_{channel[0]}_time.svg', [command, channel])
lines = ['# DATA0008 RPM / 전압 / 전류', '',
         '- 원본: `D:\\DATA0008.BIN`',
         f'- 검증된 SD 레코드: {len(records):,}개; 누락 카운터: {sum(m for _,_,m,_ in records):,}개',
         f'- 시간축: SD 기록 시작 기준 {times[0]:.3f}~{times[-1]:.4f}초',
         '- RPM: 펌웨어 RPM 필드. 전압·전류: 내장 thruster report의 voltage_edf/current_edf.',
         '- TMS 아날로그 전압·전류는 calibrated=1(로드셀만 보정) 상태로 NaN이므로 사용하지 않음.',
         '- 통계는 전체 SD 레코드 기준이며 같은 thruster 패킷이 반복 저장된 값도 포함함.',
         '- 기존 thrust_time.svg의 PC Start 기준 28.104초와 시간 기준/종료 시점이 다르므로 직접 겹쳐 정렬하지 않음.',
         '', '| 항목 | 유효 레코드 | 최소 | 평균 | 최대 |', '|---|---:|---:|---:|---:|']
for _, label, values, _ in channels:
    valid = [v for v in values if math.isfinite(v)]
    lines.append(f'| {label} | {len(valid):,} | {min(valid):.4f} | {statistics.mean(valid):.4f} | {max(valid):.4f} |')
lines.extend(['', '그래프: DATA0008_rpm_voltage_current_time.svg (통합), DATA0008_rpm_time.svg, DATA0008_voltage_time.svg, DATA0008_current_time.svg.', '', '각 그래프의 상단은 BIN에 기록된 적용 스로틀 명령이며 PC 요청값이 아님.'])
(OUT / 'DATA0008_rpm_voltage_current_summary.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
print('\n'.join(lines))
