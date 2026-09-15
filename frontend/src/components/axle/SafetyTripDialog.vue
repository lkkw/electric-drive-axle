<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { AlertTriangleIcon } from "@lucide/vue";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useAxleStore } from "@/stores/useAxleStore";

const axleStore = useAxleStore();
const isOpen = ref(false);
const displayedTripId = ref<number | null>(null);
const trip = computed(() => axleStore.telemetry.safety.last_trip);

watch(
  () => trip.value?.trip_id,
  (tripId) => {
    if (tripId !== undefined && tripId !== displayedTripId.value) {
      displayedTripId.value = tripId;
      isOpen.value = true;
    }
  },
  { immediate: true },
);

function acknowledge() {
  isOpen.value = false;
}
</script>

<template>
  <Dialog v-model:open="isOpen">
    <DialogContent :show-close-button="false">
      <DialogHeader>
        <DialogTitle>自动安全停机已触发</DialogTitle>
        <DialogDescription>
          上位机已记录越限事件并执行现有急停联锁。
        </DialogDescription>
      </DialogHeader>

      <Alert v-if="trip" variant="destructive">
        <AlertTriangleIcon />
        <AlertTitle>越限原因</AlertTitle>
        <AlertDescription>
          {{ trip.message }}
        </AlertDescription>
      </Alert>

      <DialogDescription>
        请现场确认 MCU
        与台架已进入安全状态。此弹窗仅确认上位机软件已发出停机请求，不能替代硬件安全状态确认。
      </DialogDescription>

      <DialogFooter>
        <Button type="button" @click="acknowledge"> 我已知悉 </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
