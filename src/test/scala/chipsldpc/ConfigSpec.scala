package chipsldpc

import org.scalatest.freespec.AnyFreeSpec

final class ConfigSpec extends AnyFreeSpec {
  "Relay defaults use four-bit messages and seven-bit marginals" in {
    assert(RelayDefaults.q == Quantization(4, 7))
    assert(RelayDefaults.scale == RampScale(4))
    assert(RelayDefaults.priorScale == 2)
    assert(RelayDefaults.memoryScale == 8)
  }

  "LLR priors use the locked scale and saturate to four bits" in {
    assert(StaticGolden.prior(0.2) == 3)
    assert(StaticGolden.prior(0.1) == 4)
    assert(StaticGolden.prior(0.001) == 14)
    assert(StaticGolden.prior(1e-4) == 15)
  }
}
