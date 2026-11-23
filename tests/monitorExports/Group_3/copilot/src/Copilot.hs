import           Copilot.Compile.C99
import           Copilot.Language              hiding (prop)
import           Copilot.Language.Prelude
import           Copilot.Library.LTL           (next)
import           Copilot.Library.MTL           hiding (since, alwaysBeen, trigger)
import           Copilot.Library.PTLTL         (since, previous, alwaysBeen)
import qualified Copilot.Library.PTLTL         as PTLTL
import qualified Copilot.Library.MTL           as MTL
import           Copilot.Library.StateMachines (stateMachine)
import           Language.Copilot              (reify)
import           Prelude                       hiding ((&&), (||), (++), (<=), (>=), (<), (>), (==), (/=), not)

alert :: Stream (Bool)
alert = extern "alert" Nothing

classifier :: Stream (Int32)
classifier = extern "classifier" Nothing

distance_to_target :: Stream (Int32)
distance_to_target = extern "distance_to_target" Nothing

halt :: Stream (Bool)
halt = extern "halt" Nothing

slowdown :: Stream (Bool)
slowdown = extern "slowdown" Nothing

state :: Stream (Int32)
state = extern "state" Nothing

turnoffUVC :: Stream (Bool)
turnoffUVC = extern "turnoffUVC" Nothing
dgt_3 :: Stream (Bool)
dgt_3 = distance_to_target > constant 3

dgt_7 :: Stream (Bool)
dgt_7 = distance_to_target > constant 7
-- | state_req101
--   @
--   
--   @
propState_req101 :: Stream Bool
propState_req101 = (PTLTL.alwaysBeen ((classifier == 1) ==> (dgt_7 ==> (state == 1))))

-- | dtt_assumption
--   @
--   
--   @
propDtt_assumption :: Stream Bool
propDtt_assumption = (PTLTL.alwaysBeen ((not (classifier == 0)) ==> (distance_to_target >= 0)))

-- | state_req201
--   @
--   
--   @
propState_req201 :: Stream Bool
propState_req201 = (PTLTL.alwaysBeen ((classifier == 2) ==> (dgt_7 ==> (state == 2))))

-- | state_req202
--   @
--   
--   @
propState_req202 :: Stream Bool
propState_req202 = (PTLTL.alwaysBeen ((classifier == 2) ==> (((not dgt_7) && dgt_3) ==> (state == 3))))

-- | state_req203
--   @
--   
--   @
propState_req203 :: Stream Bool
propState_req203 = (PTLTL.alwaysBeen ((classifier == 2) ==> ((not dgt_3) ==> (state == 3))))

-- | state_req102
--   @
--   
--   @
propState_req102 :: Stream Bool
propState_req102 = (PTLTL.alwaysBeen ((classifier == 1) ==> (((not dgt_7) && dgt_3) ==> (state == 2))))

-- | classifier_empty
--   @
--   
--   @
propClassifier_empty :: Stream Bool
propClassifier_empty = (PTLTL.alwaysBeen ((classifier == 0) ==> (state == 0)))

-- | operationalstate_1
--   @
--   
--   @
propOperationalstate_1 :: Stream Bool
propOperationalstate_1 = (PTLTL.alwaysBeen ((state == 1) ==> (((slowdown && (not halt)) && alert) && (not turnoffUVC))))

-- | classifier_assumption
--   @
--   
--   @
propClassifier_assumption :: Stream Bool
propClassifier_assumption = (PTLTL.alwaysBeen (((classifier == 0) `xor` (classifier == 1)) `xor` (classifier == 2)))

-- | state_req103
--   @
--   
--   @
propState_req103 :: Stream Bool
propState_req103 = (PTLTL.alwaysBeen ((classifier == 1) ==> ((not dgt_3) ==> (state == 3))))

-- | operationalstate_3_1
--   @
--   
--   @
propOperationalstate_3_1 :: Stream Bool
propOperationalstate_3_1 = (PTLTL.alwaysBeen ((state == 3) ==> (not slowdown)))

-- | operationalstate_3_2
--   @
--   
--   @
propOperationalstate_3_2 :: Stream Bool
propOperationalstate_3_2 = (PTLTL.alwaysBeen ((state == 3) ==> halt))

-- | operationalstate_3_3
--   @
--   
--   @
propOperationalstate_3_3 :: Stream Bool
propOperationalstate_3_3 = (PTLTL.alwaysBeen ((state == 3) ==> alert))

-- | operationalstate_3_4
--   @
--   
--   @
propOperationalstate_3_4 :: Stream Bool
propOperationalstate_3_4 = (PTLTL.alwaysBeen ((state == 3) ==> turnoffUVC))

-- | operationalstate_2_1
--   @
--   
--   @
propOperationalstate_2_1 :: Stream Bool
propOperationalstate_2_1 = (PTLTL.alwaysBeen ((state == 2) ==> (not slowdown)))

-- | operationalstate_2_2
--   @
--   
--   @
propOperationalstate_2_2 :: Stream Bool
propOperationalstate_2_2 = (PTLTL.alwaysBeen ((state == 2) ==> halt))

-- | operationalstate_2_3
--   @
--   
--   @
propOperationalstate_2_3 :: Stream Bool
propOperationalstate_2_3 = (PTLTL.alwaysBeen ((state == 2) ==> alert))

-- | operationalstate_2_4
--   @
--   
--   @
propOperationalstate_2_4 :: Stream Bool
propOperationalstate_2_4 = (PTLTL.alwaysBeen ((state == 2) ==> (not turnoffUVC)))

-- | operationalstate_0_1
--   @
--   
--   @
propOperationalstate_0_1 :: Stream Bool
propOperationalstate_0_1 = (PTLTL.alwaysBeen ((state == 0) ==> (not slowdown)))

-- | operationalstate_0_2
--   @
--   
--   @
propOperationalstate_0_2 :: Stream Bool
propOperationalstate_0_2 = (PTLTL.alwaysBeen ((state == 0) ==> (not halt)))

-- | operationalstate_0_3
--   @
--   
--   @
propOperationalstate_0_3 :: Stream Bool
propOperationalstate_0_3 = (PTLTL.alwaysBeen ((state == 0) ==> (not alert)))

-- | operationalstate_0_4
--   @
--   
--   @
propOperationalstate_0_4 :: Stream Bool
propOperationalstate_0_4 = (PTLTL.alwaysBeen ((state == 0) ==> (not turnoffUVC)))

-- | Clock that increases in one-unit steps.
clock :: Stream Int64
clock = [0] ++ (clock + 1)

-- | First Time Point
ftp :: Stream Bool
ftp = [True] ++ false

pre :: Stream Bool -> Stream Bool
pre = ([False] ++)

tpre :: Stream Bool -> Stream Bool
tpre = ([True] ++)

notPreviousNot :: Stream Bool -> Stream Bool
notPreviousNot = not . PTLTL.previous . not

-- | Complete specification. Calls C handler functions when properties are
-- violated.
spec :: Spec
spec = do
  trigger "handlerState_req101" (not propState_req101) []
  trigger "handlerDtt_assumption" (not propDtt_assumption) []
  trigger "handlerState_req201" (not propState_req201) []
  trigger "handlerState_req202" (not propState_req202) []
  trigger "handlerState_req203" (not propState_req203) []
  trigger "handlerState_req102" (not propState_req102) []
  trigger "handlerClassifier_empty" (not propClassifier_empty) []
  trigger "handlerOperationalstate_1" (not propOperationalstate_1) []
  trigger "handlerClassifier_assumption" (not propClassifier_assumption) []
  trigger "handlerState_req103" (not propState_req103) []
  trigger "handlerOperationalstate_3_1" (not propOperationalstate_3_1) []
  trigger "handlerOperationalstate_3_2" (not propOperationalstate_3_2) []
  trigger "handlerOperationalstate_3_3" (not propOperationalstate_3_3) []
  trigger "handlerOperationalstate_3_4" (not propOperationalstate_3_4) []
  trigger "handlerOperationalstate_2_1" (not propOperationalstate_2_1) []
  trigger "handlerOperationalstate_2_2" (not propOperationalstate_2_2) []
  trigger "handlerOperationalstate_2_3" (not propOperationalstate_2_3) []
  trigger "handlerOperationalstate_2_4" (not propOperationalstate_2_4) []
  trigger "handlerOperationalstate_0_1" (not propOperationalstate_0_1) []
  trigger "handlerOperationalstate_0_2" (not propOperationalstate_0_2) []
  trigger "handlerOperationalstate_0_3" (not propOperationalstate_0_3) []
  trigger "handlerOperationalstate_0_4" (not propOperationalstate_0_4) []

main :: IO ()
main = reify spec >>= compile "copilot"
