import unittest
from scripts.ds1_ssi_fastconnect import normalize
class SSIFastConnectTests(unittest.TestCase):
 def test_case_insensitive_fields_and_adjusted_close(self):
  o=[{"TradingDate":"08/10/2026","Open":"28000","High":"28500","Low":"27000","Close":"28000","Volume":"12345","Market":"HOSE"}]
  q=[{"Tradingdate":"08/10/2026","Closeprice":"28000","Closepriceadjusted":"21538.46","Refprice":"27500"}]
  out=normalize(o,q,"HDB")
  self.assertEqual(len(out),1)
  self.assertAlmostEqual(out[0]["price_close_factor"],21538.46/28000)
  self.assertEqual(out[0]["raw_volume"],12345)
  self.assertFalse("adjusted_volume" in out[0])
if __name__=="__main__":unittest.main()
