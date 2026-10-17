import tempfile
import unittest
from pathlib import Path
from normalize_ucla_trees import normalize_csv


class TreeNormalizationTests(unittest.TestCase):
    def test_measured_units_and_missing_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "trees.csv"
            csv_path.write_text(
                'Latitude,Longitude,Height Feet,Crown Spread Feet\n'
                '34.0728,-118.4422,40,20\n'
                '34.0729,-118.4421,,14\n'
                'NOTLAT,-118.44,40,20\n', encoding='utf-8')
            data, report = normalize_csv(
                csv_path, lat_col='Latitude', lon_col='Longitude',
                height_col='Height Feet', crown_col='Crown Spread Feet',
                unit='ft', source='permissioned test fixture')
            self.assertEqual(report['features'], 2)
            self.assertEqual(report['rejected_rows'], 1)
            self.assertEqual(report['shade_model_ready'], 1)
            p0 = data['features'][0]['properties']
            self.assertAlmostEqual(p0['height_m'], 12.192)
            self.assertAlmostEqual(p0['crown_radius_m'], 3.048)
            self.assertFalse(data['features'][1]['properties']['shade_model_ready'])


if __name__ == '__main__':
    unittest.main()
