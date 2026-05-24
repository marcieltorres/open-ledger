from src.model.enums import ClearingNetwork

ACC_RECEIVABLES = "1.1.001"
ACC_RECEIVABLES_ANTICIPATED = "1.1.002"
ACC_ANTICIPATION_FEE = "4.1.003"
ACC_TRANSFER = "9.9.998"

WORLD_ACCOUNTS: dict[ClearingNetwork, str] = {
    ClearingNetwork.STR: "9.9.901",
    ClearingNetwork.CIP_PIX: "9.9.902",
    ClearingNetwork.COMPE: "9.9.903",
}
