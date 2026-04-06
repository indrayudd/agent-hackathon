import DropZone from "@/components/upload/DropZone";

export default function Home() {
  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-white">
      <h1 className="text-4xl font-bold text-gray-900 mb-2">AgenticEDA</h1>
      <p className="text-gray-500 mb-10">Upload a dataset to begin</p>
      <DropZone />
    </div>
  );
}
