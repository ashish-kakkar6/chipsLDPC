package chipsldpc

import org.scalatest.freespec.AnyFreeSpec

final class ConfigSpec extends AnyFreeSpec {
  "legacy vanilla defaults remain unchanged" in {
    assert(RelayDefaults.q == Quantization(4, 7))
    assert(RelayDefaults.scale == RampScale(4))
    assert(RelayDefaults.priorScale == 2)
    assert(RelayDefaults.memoryScale == 8)
  }

  "the FPGA-paper Relay arithmetic profile is named independently" in {
    assert(RelayDefaults.paperQ == Quantization(4, 5))
    assert(RelayDefaults.paperFormat == RelayFormat(4, 3))
  }

  "LLR priors use the locked scale and saturate to four bits" in {
    assert(StaticGolden.prior(0.2) == 3)
    assert(StaticGolden.prior(0.1) == 4)
    assert(StaticGolden.prior(0.001) == 14)
    assert(StaticGolden.prior(1e-4) == 15)
  }
}
