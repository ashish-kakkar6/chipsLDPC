package chipsldpc

import chisel3._
import chisel3.simulator.scalatest.ChiselSim
import chipsldpc.graph.{TannerGraph, TannerNodeGraphs}
import org.scalatest.freespec.AnyFreeSpec

final class StaticTannerDatapathSpec extends AnyFreeSpec with ChiselSim {
  private val graph = TannerGraph.fromRows(
    7,
    Seq(Seq(3, 4, 5, 6), Seq(1, 2, 5, 6), Seq(0, 2, 4, 6)),
  )
  private val nodes = TannerNodeGraphs.from(graph)
  private val q = RelayDefaults.q
  private val priors = Vector(1, 2, 3, 4, 5, 6, 7)

  private def load(
      dut: StaticTannerDatapath,
      syndrome: Seq[Boolean],
  ): Reference.DecoderState = {
    syndrome.zipWithIndex.foreach { case (bit, i) => dut.io.load.bits.syndrome(i).poke(bit.B) }
    priors.zipWithIndex.foreach { case (prior, i) => dut.io.load.bits.prior(i).poke(prior.U) }
    dut.io.load.valid.poke(true.B)
    dut.io.load.ready.expect(true.B)
    dut.clock.step()
    dut.io.load.valid.poke(false.B)
    dut.io.result.valid.expect(false.B)
    Reference.initialize(nodes, priors, q)
  }

  private def step(
      dut: StaticTannerDatapath,
      iteration: Int,
      expected: Reference.DecoderState,
      syndrome: Seq[Boolean],
  ): Unit = {
    dut.io.step.bits.poke(iteration.U)
    dut.io.step.valid.poke(true.B)
    dut.io.step.ready.expect(true.B)
    dut.clock.step()
    dut.io.step.valid.poke(false.B)
    dut.io.result.valid.expect(false.B)
    dut.clock.step()
    dut.io.result.valid.expect(true.B)

    expected.marginal.zipWithIndex.foreach { case (value, i) =>
      dut.io.result.bits.marginal(i).expect(value.S)
      dut.io.result.bits.decision(i).expect(expected.decision(i).B)
    }
    val residual = Reference.residual(nodes, expected, syndrome)
    residual.zipWithIndex.foreach { case (bit, i) => dut.io.result.bits.residual(i).expect(bit.B) }
    dut.io.result.bits.converged.expect((!residual.contains(true)).B)
  }

  "the reference model initializes each edge from its variable prior" in {
    val state = Reference.initialize(nodes, priors, q)
    assert(state.v2c == graph.edges.map(edge => Reference.SignMag(false, priors(edge.variable))))
  }

  "the static Steane graph matches the reference every two cycles" in {
    simulate(new StaticTannerDatapath(nodes)) { dut =>
      dut.io.load.valid.poke(false.B)
      dut.io.step.valid.poke(false.B)
      dut.io.step.bits.poke(0.U)
      dut.reset.poke(true.B)
      dut.clock.step()
      dut.reset.poke(false.B)

      dut.io.step.valid.poke(true.B)
      dut.io.step.ready.expect(false.B)
      dut.io.step.valid.poke(false.B)

      for (word <- 0 until 8) {
        val syndrome = Vector.tabulate(graph.checkCount)(i => ((word >> i) & 1) != 0)
        var expected = load(dut, syndrome)
        for (iteration <- 1 to 4) {
          expected = Reference.iterate(nodes, expected, syndrome, priors, iteration, q, RelayDefaults.scale)
          step(dut, iteration, expected, syndrome)
        }
      }
    }
  }
}
