package chipsldpc.GaussJordan

import chisel3._
import chisel3.simulator.scalatest.ChiselSim
import org.scalatest.freespec.AnyFreeSpec

final class GaussJordanPESpec extends AnyFreeSpec with ChiselSim {
  private val opcodes = Seq(GjOpcode.Pass, GjOpcode.Swap, GjOpcode.Add, GjOpcode.Lock)

  private def reset(dut: PeCol): Unit = {
    dut.en_i.poke(true.B)
    dut.data_i.poke(false.B)
    dut.op_i.poke(GjOpcode.Pass)
    dut.rst.poke(true.B)
    dut.clk.step()
    dut.rst.poke(false.B)
  }

  private def reset(dut: PeDiag): Unit = {
    dut.en_i.poke(true.B)
    dut.data_i.poke(false.B)
    dut.reduce_sig_i.poke(false.B)
    dut.rst.poke(true.B)
    dut.clk.step()
    dut.rst.poke(false.B)
  }

  "opcodes retain their legacy two-bit encodings" in {
    opcodes.zipWithIndex.foreach { case (op, value) =>
      assert(op.litValue == BigInt(value))
    }
  }

  "PeCol implements all 16 transitions" in {
    simulateRaw(new PeCol) { dut =>
      for {
        state <- Seq(false, true)
        data <- Seq(false, true)
        op <- opcodes
      } {
        reset(dut)
        if (state) {
          dut.data_i.poke(true.B)
          dut.op_i.poke(GjOpcode.Lock)
          dut.clk.step()
        }
        dut.data_i.poke(data.B)
        dut.op_i.poke(op)
        dut.clk.step()

        val loads = op == GjOpcode.Swap || op == GjOpcode.Lock
        val nextState = if (loads) data else state
        val nextData =
          if (op == GjOpcode.Add) state ^ data else if (loads) state else data
        dut.state_o.expect(nextState.B)
        dut.data_o.expect(nextData.B)
        dut.op_o.expect(op)
      }
    }
  }

  "PeDiag implements all 8 transitions" in {
    simulateRaw(new PeDiag) { dut =>
      for {
        reduce <- Seq(false, true)
        state <- Seq(false, true)
        data <- Seq(false, true)
      } {
        reset(dut)
        if (state) {
          dut.data_i.poke(true.B)
          dut.clk.step()
        }
        dut.data_i.poke(data.B)
        dut.reduce_sig_i.poke(reduce.B)
        dut.reduce_sig_o.expect(reduce.B)
        dut.clk.step()

        val swap = reduce && state
        val nextState = state || (data && !reduce)
        val op =
          if (swap) GjOpcode.Swap
          else if (reduce) GjOpcode.Pass
          else if (!data) GjOpcode.Pass
          else if (!state) GjOpcode.Lock
          else GjOpcode.Add
        dut.state_o.expect(nextState.B)
        dut.data_o.expect((reduce && data).B)
        dut.op_o.expect(op)
      }
    }
  }

  "disabled processing elements hold registered outputs" in {
    simulateRaw(new PeCol) { dut =>
      reset(dut)
      dut.data_i.poke(true.B)
      dut.op_i.poke(GjOpcode.Lock)
      dut.clk.step()
      dut.en_i.poke(false.B)
      dut.data_i.poke(false.B)
      dut.op_i.poke(GjOpcode.Swap)
      dut.clk.step()
      dut.state_o.expect(true.B)
      dut.data_o.expect(false.B)
      dut.op_o.expect(GjOpcode.Lock)
    }

    simulateRaw(new PeDiag) { dut =>
      reset(dut)
      dut.en_i.poke(false.B)
      dut.data_i.poke(true.B)
      dut.clk.step()
      dut.state_o.expect(false.B)
      dut.data_o.expect(false.B)
      dut.op_o.expect(GjOpcode.Pass)

      dut.en_i.poke(true.B)
      dut.clk.step()
      dut.en_i.poke(false.B)
      dut.reduce_sig_i.poke(true.B)
      dut.reduce_sig_o.expect(true.B)
      dut.clk.step()
      dut.state_o.expect(true.B)
      dut.data_o.expect(false.B)
      dut.op_o.expect(GjOpcode.Lock)
    }
  }

  "reset has priority and reduction forwarding stays combinational" in {
    simulateRaw(new PeCol) { dut =>
      reset(dut)
      dut.data_i.poke(true.B)
      dut.op_i.poke(GjOpcode.Lock)
      dut.clk.step()
      dut.rst.poke(true.B)
      dut.state_o.expect(true.B)
      dut.data_o.expect(false.B)
      dut.op_o.expect(GjOpcode.Lock)
      dut.clk.step()
      dut.state_o.expect(false.B)
      dut.data_o.expect(false.B)
      dut.op_o.expect(GjOpcode.Pass)
    }

    simulateRaw(new PeDiag) { dut =>
      reset(dut)
      dut.data_i.poke(true.B)
      dut.clk.step()
      dut.state_o.expect(true.B)
      dut.en_i.poke(true.B)
      dut.reduce_sig_i.poke(true.B)
      dut.reduce_sig_o.expect(true.B)
      dut.rst.poke(true.B)
      dut.reduce_sig_o.expect(false.B)
      dut.state_o.expect(true.B)
      dut.data_o.expect(false.B)
      dut.op_o.expect(GjOpcode.Lock)
      dut.clk.step()
      dut.state_o.expect(false.B)
      dut.data_o.expect(false.B)
      dut.op_o.expect(GjOpcode.Pass)
    }
  }
}
