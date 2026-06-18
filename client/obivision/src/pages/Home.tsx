import { Link } from "wouter";
import { Button } from "@/components/ui/button";
import obigoCI from "@/asset/Obigo_CI_vertical_for_web(306x500).png";

export default function Home() {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-gray-50 px-4">
      <div className="flex flex-col items-center gap-6 max-w-md w-full">
        <img
          src={obigoCI}
          alt="Obigo"
          className="h-20 object-contain mb-4"
        />

        <div className="text-center space-y-2">
          <h1 className="text-2xl font-semibold text-gray-900">
            차량 파손 사진을 분석해
          </h1>
          <p className="text-lg text-gray-600">
            예상 수리 견적을 알려드리겠습니다
          </p>
        </div>

        <Link href="/request">
          <Button size="lg" className="w-64 text-base">
            시작하기
          </Button>
        </Link>
      </div>
    </div>
  );
}
