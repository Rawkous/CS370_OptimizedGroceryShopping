'use client';
import Image from 'next/image';
import { useState } from 'react';

export default function InteractiveImage() {
    const [isVisible, setIsVisible] = useState(true);
    const [scale, setScale] = useState(1);
    const [border, setBorder] = useState(false);

    return (
        <main className="flex flex-col items-center justify-center min-h-screen bg-gray-100 p-6">
            <h1 className="text-3xl font-bold mb-4">Interactive Image Example</h1>

            {isVisible && (
                <div
                    className={`transition-transform duration-300 ${
                        border ? 'border-4 border-blue-500 rounded-xl' : ''
                    }`}
                    style={{ transform: `scale(${scale})` }}
                >
                    <Image
                        src="/myImage.png" // 👈 your local image in the same folder
                        alt="My Local Image"
                        width={400}
                        height={400}
                        className="rounded-lg shadow-lg"
                    />
                </div>
            )}

            <div className="mt-6 flex gap-4">
                <button
                    onClick={() => setIsVisible(!isVisible)}
                    className="px-4 py-2 bg-indigo-600 text-white rounded hover:bg-indigo-700"
                >
                    {isVisible ? 'Hide' : 'Show'} Image
                </button>

                <button
                    onClick={() => setScale(prev => (prev === 1 ? 1.2 : 1))}
                    className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700"
                >
                    Zoom
                </button>

                <button
                    onClick={() => setBorder(!border)}
                    className="px-4 py-2 bg-pink-600 text-white rounded hover:bg-pink-700"
                >
                    Toggle Border
                </button>
            </div>
        </main>
    );
}
