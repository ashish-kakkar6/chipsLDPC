package chipsldpc

import chisel3._
import chisel3.util.{Cat, Decoupled, Enum, OHToUInt, PriorityEncoderOH, log2Ceil}

final case class SparseBitmaskStreamerConfig(size: Int, bankWidth: Int = 64) {
  require(size > 0, "bitmask size must be positive")
  require(bankWidth > 1 && (bankWidth & (bankWidth - 1)) == 0,
    "bank width must be a power of two")

  val indexBits: Int = math.max(1, log2Ceil(size))
  val bankCount: Int = (size + bankWidth - 1) / bankWidth
  val bankIndexBits: Int = math.max(1, log2Ceil(bankCount))
  val bitIndexBits: Int = log2Ceil(bankWidth)
  val paddedSize: Int = bankCount * bankWidth
}

/** One asserted bit from a snapshotted bitmask. Unreported indices are zero. */
final class SparseBitmaskEntry(config: SparseBitmaskStreamerConfig) extends Bundle {
  val index = UInt(config.indexBits.W)
  val last = Bool()
}

/** Snapshot a dense bitmask and emit its asserted indices in ascending order. */
final class SparseBitmaskStreamer(config: SparseBitmaskStreamerConfig) extends Module {
  val io = IO(new Bundle {
    val in = Flipped(Decoupled(UInt(config.size.W)))
    val out = Decoupled(new SparseBitmaskEntry(config))
    val done = Decoupled(Bool())
  })

  private val sIdle :: sSelect :: sEmit :: sDone :: Nil = Enum(4)
  private val state = RegInit(sIdle)
  private val banks = Reg(Vec(config.bankCount, UInt(config.bankWidth.W)))
  private val pendingBanks = RegInit(0.U(config.bankCount.W))
  private val activeBank = Reg(UInt(config.bankIndexBits.W))
  private val activeWord = Reg(UInt(config.bankWidth.W))

  private val padding = config.paddedSize - config.size
  private val paddedInput = if (padding == 0) io.in.bits else Cat(0.U(padding.W), io.in.bits)
  private val inputBanks = Seq.tabulate(config.bankCount) { bank =>
    paddedInput((bank + 1) * config.bankWidth - 1, bank * config.bankWidth)
  }
  private val inputNonEmpty = VecInit(inputBanks.map(_.orR)).asUInt

  private val nextBankOH = PriorityEncoderOH(pendingBanks)
  private val nextBank = OHToUInt(nextBankOH)
  private val nextBitOH = PriorityEncoderOH(activeWord)
  private val nextBit = OHToUInt(nextBitOH)
  private val remainingWord = activeWord & ~nextBitOH
  private val fullIndex = Cat(activeBank, nextBit)

  io.in.ready := state === sIdle
  io.out.valid := state === sEmit
  io.out.bits.index := fullIndex(config.indexBits - 1, 0)
  io.out.bits.last := state === sEmit && !remainingWord.orR && !pendingBanks.orR
  io.done.valid := state === sDone
  io.done.bits := true.B

  when(io.in.fire) {
    banks.zip(inputBanks).foreach { case (bank, value) => bank := value }
    pendingBanks := inputNonEmpty
    state := Mux(inputNonEmpty.orR, sSelect, sDone)
  }.elsewhen(state === sSelect) {
    assert(pendingBanks.orR)
    activeBank := nextBank
    activeWord := banks(nextBank)
    pendingBanks := pendingBanks & ~nextBankOH
    state := sEmit
  }.elsewhen(io.out.fire) {
    assert(activeWord.orR)
    when(remainingWord.orR) {
      activeWord := remainingWord
    }.elsewhen(pendingBanks.orR) {
      state := sSelect
    }.otherwise {
      state := sDone
    }
  }.elsewhen(io.done.fire) {
    state := sIdle
  }
}
