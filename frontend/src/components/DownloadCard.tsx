import { colorPallete } from "@/styles/constants";
import Link from "next/link";

type AboutCardProps = {
    title: string
    img_path: string
    info: string
    redirect: string
}


const DownloadCard = ({ title, img_path, info, redirect }: AboutCardProps) => {
    return (
        <div className="max-w-sm bg-white border border-gray-200 rounded-lg shadow">
            <Link href="#">
                <img className="rounded-t-lg" src={img_path} alt=""  width='100%' height='100%'/>
            </Link>
            <div className="p-5">
                <Link href="#">
                    <h5 className="mb-2 text-2xl font-bold tracking-tight text-gray-900">{title}</h5>
                </Link>
                <p className="mb-3 font-normal text-gray-700">{info}</p>
                <Link href={redirect} style={{ backgroundColor: colorPallete['primary'] }} className="inline-flex items-center px-3 py-2 text-sm font-medium text-center text-white rounded-lg hover:bg-blue-800 focus:ring-4 focus:outline-none focus:ring-blue-300">
                    More
                    <svg className="rtl:rotate-180 w-3.5 h-3.5 ms-2" aria-hidden="true" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 14 10">
                        <path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M1 5h12m0 0L9 1m4 4L9 9"/>
                    </svg>
                </Link>
            </div>
        </div>
    );

};

export default DownloadCard;